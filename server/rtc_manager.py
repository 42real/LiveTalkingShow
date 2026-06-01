###############################################################################
#  WebRTC 连接管理 + RTC 音频/视频接收
###############################################################################

import json
import asyncio
import random
import copy
from typing import Dict, Optional
import queue

from aiohttp import web
from aiortc import RTCPeerConnection, RTCSessionDescription, RTCIceServer, RTCConfiguration, RTCBundlePolicy
from aiortc.rtcrtpsender import RTCRtpSender

from utils.logger import logger


# def _rand_session_id(n: int = 6) -> int:
#     """生成 N 位随机 session ID"""
#     return random.randint(10 ** (n - 1), 10 ** n - 1)


from server.session_manager import session_manager

class RTCManager:
    """
    WebRTC 连接管理器。
    
    管理 PeerConnection 生命周期、音视频轨道收发、DataChannel。
    """

    def __init__(self, opt):
        """
        Args:
            opt: 全局配置
        """
        self.opt = opt
        self.pcs: set = set()

    async def handle_offer(self, request):
        """处理 WebRTC offer 信令"""
        params = await request.json()
        offer = RTCSessionDescription(sdp=params["sdp"], type=params["type"])

        if False: # 不再由 RTCManager 控制 max_session，让业务逻辑或SessionManager 控制
            logger.info('reach max session')
            return web.Response(
                content_type="application/json",
                text=json.dumps({"code": -1, "msg": "reach max session"}),
            )

        #sessionid = _rand_session_id()

        # 通过 SessionManager 构建
        sessionid = await session_manager.create_session(params)
        logger.info('offer sessionid=%s', sessionid)
        avatar_session = session_manager.get_session(sessionid)

        # 创建 PeerConnection
        ice_server = RTCIceServer(urls='stun:stun.freeswitch.org:3478')
        pc = RTCPeerConnection(
            configuration=RTCConfiguration(iceServers=[ice_server])
        )
        self.pcs.add(pc)

        # 添加发送轨道
        from server.webrtc import HumanPlayer
        player = HumanPlayer(avatar_session)
        if getattr(self.opt, "alpha_output", False):
            player.start()
        pc.addTrack(player.audio)
        pc.addTrack(player.video)

        @pc.on("connectionstatechange")
        async def on_connectionstatechange():
            logger.info("Connection state is %s", pc.connectionState)
            if pc.connectionState in ("failed", "closed"):
                player.stop_worker()
                await pc.close()
                self.pcs.discard(pc)
                session_manager.remove_session(sessionid)

        # 设置编解码器偏好
        capabilities = RTCRtpSender.getCapabilities("video")
        preferences = list(filter(lambda x: x.name == "H264", capabilities.codecs))
        preferences += list(filter(lambda x: x.name == "VP8", capabilities.codecs))
        preferences += list(filter(lambda x: x.name == "rtx", capabilities.codecs))
        transceiver = pc.getTransceivers()[1]
        transceiver.setCodecPreferences(preferences)

        await pc.setRemoteDescription(offer)

        answer = await pc.createAnswer()
        await pc.setLocalDescription(answer)

        return web.Response(
            content_type="application/json",
            text=json.dumps({
                "sdp": pc.localDescription.sdp,
                "type": pc.localDescription.type,
                "sessionid": sessionid,
            }),
        )

    async def handle_alpha_offer(self, request):
        """Handle a transparent-display WebRTC offer with color + alpha tracks."""
        params = await request.json()
        offer = RTCSessionDescription(sdp=params["sdp"], type=params["type"])

        sessionid = await session_manager.create_session(params)
        logger.info("alpha webrtc offer sessionid=%s param_keys=%s", sessionid, sorted(params.keys()))
        avatar_session = session_manager.get_session(sessionid)

        ice_server = RTCIceServer(urls="stun:stun.freeswitch.org:3478")
        pc = RTCPeerConnection(
            configuration=RTCConfiguration(
                iceServers=[ice_server],
                bundlePolicy=RTCBundlePolicy.MAX_BUNDLE,
            )
        )
        self.pcs.add(pc)

        from server.alpha_webrtc import AlphaWebRTCPlayer

        player = AlphaWebRTCPlayer(avatar_session)

        @pc.on("connectionstatechange")
        async def on_connectionstatechange():
            logger.info("Alpha WebRTC connection state is %s", pc.connectionState)
            if pc.connectionState in ("failed", "closed"):
                player.stop_worker()
                await pc.close()
                self.pcs.discard(pc)
                session_manager.remove_session(sessionid)

        await pc.setRemoteDescription(offer)

        send_tracks = [player.audio, player.color_video, player.alpha_video]
        offered_transceivers = [
            transceiver
            for transceiver in pc.getTransceivers()
            if transceiver.sender.track is None and transceiver.kind in ("audio", "video")
        ]
        if len(offered_transceivers) < len(send_tracks):
            player.stop_worker()
            await pc.close()
            self.pcs.discard(pc)
            session_manager.remove_session(sessionid)
            return web.Response(
                status=400,
                content_type="application/json",
                text=json.dumps({"code": -1, "msg": "offer must contain audio + two video recvonly m-lines"}),
            )

        for transceiver, track in zip(offered_transceivers, send_tracks):
            if transceiver.kind != track.kind:
                player.stop_worker()
                await pc.close()
                self.pcs.discard(pc)
                session_manager.remove_session(sessionid)
                return web.Response(
                    status=400,
                    content_type="application/json",
                    text=json.dumps({
                        "code": -1,
                        "msg": "offer m-line order must be audio, video, video",
                    }),
                )
            transceiver.sender.replaceTrack(track)
            transceiver.direction = "sendonly"
            logger.info(
                "alpha webrtc bound track kind=%s mid=%s track_id=%s",
                track.kind,
                transceiver.mid,
                track.id,
            )

        capabilities = RTCRtpSender.getCapabilities("video")
        preferences = list(filter(lambda x: x.name == "H264", capabilities.codecs))
        preferences += list(filter(lambda x: x.name == "VP8", capabilities.codecs))
        preferences += list(filter(lambda x: x.name == "rtx", capabilities.codecs))
        for transceiver in offered_transceivers:
            if transceiver.kind == "video" and preferences:
                transceiver.setCodecPreferences(preferences)

        answer = await pc.createAnswer()
        await pc.setLocalDescription(answer)

        return web.Response(
            content_type="application/json",
            text=json.dumps({
                "sdp": pc.localDescription.sdp,
                "type": pc.localDescription.type,
                "sessionid": sessionid,
                "tracks": {
                    "audio": "audio",
                    "color": "video-0",
                    "alpha": "video-1",
                },
            }),
        )

    async def handle_rtcpush(self, push_url, sessionid: str):
        """RTCPush 模式：主动推流"""
        import aiohttp
        await session_manager.create_session({}, sessionid)
        avatar_session = session_manager.get_session(sessionid)

        pc = RTCPeerConnection()
        self.pcs.add(pc)

        @pc.on("connectionstatechange")
        async def on_connectionstatechange():
            logger.info("Connection state is %s", pc.connectionState)
            if pc.connectionState == "failed":
                await pc.close()
                self.pcs.discard(pc)

        from server.webrtc import HumanPlayer
        player = HumanPlayer(avatar_session)
        pc.addTrack(player.audio)
        pc.addTrack(player.video)

        await pc.setLocalDescription(await pc.createOffer())

        async with aiohttp.ClientSession() as session:
            async with session.post(push_url, data=pc.localDescription.sdp) as response:
                answer_sdp = await response.text()

        await pc.setRemoteDescription(
            RTCSessionDescription(sdp=answer_sdp, type='answer')
        )

    async def shutdown(self):
        """关闭所有 PeerConnection"""
        coros = [pc.close() for pc in self.pcs]
        await asyncio.gather(*coros)
        self.pcs.clear()
