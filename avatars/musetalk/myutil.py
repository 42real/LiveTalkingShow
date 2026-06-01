import numpy as np
import cv2


def _mask_to_gray(mask_array):
    if mask_array.ndim == 2:
        return mask_array
    if mask_array.ndim == 3 and mask_array.shape[2] == 4:
        return mask_array[:, :, 3]
    return cv2.cvtColor(mask_array, cv2.COLOR_BGR2GRAY)


def get_image_blending(image,face,face_box,mask_array,crop_box):
    body = image
    x, y, x1, y1 = [int(v) for v in face_box]
    x_s, y_s, x_e, y_e = [int(v) for v in crop_box]
    height, width = body.shape[:2]

    crop_x0 = max(0, x_s)
    crop_y0 = max(0, y_s)
    crop_x1 = min(width, x_e)
    crop_y1 = min(height, y_e)
    if crop_x1 <= crop_x0 or crop_y1 <= crop_y0:
        return body

    face_x0 = max(x, crop_x0)
    face_y0 = max(y, crop_y0)
    face_x1 = min(x1, crop_x1)
    face_y1 = min(y1, crop_y1)
    if face_x1 <= face_x0 or face_y1 <= face_y0:
        return body

    face_large = body[crop_y0:crop_y1, crop_x0:crop_x1].copy()
    src_x0 = max(0, face_x0 - x)
    src_y0 = max(0, face_y0 - y)
    src_x1 = min(face.shape[1], src_x0 + (face_x1 - face_x0))
    src_y1 = min(face.shape[0], src_y0 + (face_y1 - face_y0))
    dst_x0 = face_x0 - crop_x0
    dst_y0 = face_y0 - crop_y0
    dst_x1 = dst_x0 + (src_x1 - src_x0)
    dst_y1 = dst_y0 + (src_y1 - src_y0)
    if src_x1 <= src_x0 or src_y1 <= src_y0 or dst_x1 <= dst_x0 or dst_y1 <= dst_y0:
        return body
    face_large[dst_y0:dst_y1, dst_x0:dst_x1] = face[src_y0:src_y1, src_x0:src_x1]

    mask_image = _mask_to_gray(mask_array)
    crop_width = max(1, x_e - x_s)
    crop_height = max(1, y_e - y_s)
    if mask_image.shape[:2] != (crop_height, crop_width):
        mask_image = cv2.resize(mask_image, (crop_width, crop_height), interpolation=cv2.INTER_LINEAR)
    mask_x0 = crop_x0 - x_s
    mask_y0 = crop_y0 - y_s
    mask_x1 = mask_x0 + face_large.shape[1]
    mask_y1 = mask_y0 + face_large.shape[0]
    mask_image = mask_image[mask_y0:mask_y1, mask_x0:mask_x1]
    if mask_image.shape[:2] != face_large.shape[:2]:
        mask_image = cv2.resize(mask_image, (face_large.shape[1], face_large.shape[0]), interpolation=cv2.INTER_LINEAR)
    mask_image = (mask_image/255).astype(np.float32)

    # mask_not = cv2.bitwise_not(mask_array)
    # prospect_tmp = cv2.bitwise_and(face_large, face_large, mask=mask_array)
    # background_img = body[y_s:y_e, x_s:x_e]
    # background_img = cv2.bitwise_and(background_img, background_img, mask=mask_not)
    # body[y_s:y_e, x_s:x_e] = prospect_tmp + background_img

    #print(mask_image.shape)
    #print(cv2.minMaxLoc(mask_image))

    body[crop_y0:crop_y1, crop_x0:crop_x1] = cv2.blendLinear(face_large,body[crop_y0:crop_y1, crop_x0:crop_x1],mask_image,1-mask_image)

    #body.paste(face_large, crop_box[:2], mask_image)
    return body
