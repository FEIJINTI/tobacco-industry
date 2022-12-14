import os
import numpy as np
from models import SpecDetector, PixelWisedDetector
from root_dir import ROOT_DIR
from multiprocessing import Process, Queue

nrows, ncols, nbands = 256, 1024, 4
img_fifo_path = "/tmp/dkimg.fifo"
mask_fifo_path = "/tmp/dkmask.fifo"
cmd_fifo_path = '/tmp/tobacco_cmd.fifo'

pxl_model_path = "rf_1x1_c4_1_sen1_4.model"
blk_model_path = "rf_8x8_c4_185_sen32_4.model"


def main(pxl_model_path=pxl_model_path, blk_model_path=blk_model_path):
    # 启动两个模型线程
    blk_cmd_queue, pxl_cmd_queue = Queue(maxsize=100), Queue(maxsize=100)
    blk_img_queue, pxl_img_queue = Queue(maxsize=100), Queue(maxsize=100)
    blk_msk_queue, pxl_msk_queue = Queue(maxsize=100), Queue(maxsize=100)
    blk_process = Process(target=block_model, args=(blk_cmd_queue, blk_img_queue, blk_msk_queue, blk_model_path, ))
    pxl_process = Process(target=pixel_model, args=(pxl_cmd_queue, pxl_img_queue, pxl_msk_queue, pxl_model_path, ))
    blk_process.start()
    pxl_process.start()
    total_len = nrows * ncols * nbands * 4
    if not os.access(img_fifo_path, os.F_OK):
        os.mkfifo(img_fifo_path, 0o777)
    if not os.access(mask_fifo_path, os.F_OK):
        os.mkfifo(mask_fifo_path, 0o777)
    data = b''
    while True:
        fd_img = os.open(img_fifo_path, os.O_RDONLY)
        while len(data) < total_len:
            data += os.read(fd_img, total_len)
        if len(data) > total_len:
            data_total = data[:total_len]
            data = data[total_len:]
        else:
            data_total = data
            data = b''
        os.close(fd_img)

        img = np.frombuffer(data_total, dtype=np.float32).reshape((nrows, nbands, -1)).transpose(0, 2, 1)
        print(f"get img shape {img.shape}")
        pxl_img_queue.put(img)
        blk_img_queue.put(img)
        pxl_msk = pxl_msk_queue.get()
        blk_msk = blk_msk_queue.get()
        mask = pxl_msk & blk_msk
        print(f"predict success get mask shape: {mask.shape}")
        # 写出
        fd_mask = os.open(mask_fifo_path, os.O_WRONLY)
        os.write(fd_mask, mask.tobytes())
        os.close(fd_mask)


def block_model(cmd_queue: Queue, img_queue: Queue, mask_queue: Queue, blk_model_path=blk_model_path):
    blk_model = SpecDetector(os.path.join(ROOT_DIR, "models", blk_model_path), blk_sz=8, channel_num=4)
    _ = blk_model.predict(np.ones((nrows, ncols, nbands)))
    rigor_rate = 70
    while True:
        # deal with the cmd if cmd_queue is not empty
        if not cmd_queue.empty():
            cmd = cmd_queue.get()
            if isinstance(cmd, int):
                rigor_rate = cmd
            elif isinstance(cmd, str):
                if cmd == 'stop':
                    break
                else:
                    try:
                        blk_model_path = SpecDetector(os.path.join(ROOT_DIR, "models", blk_model_path),
                                                      blk_sz=8, channel_num=4)
                    except Exception as e:
                        print(f"Load Model Failed! {e}")
        # deal with the img if img_queue is not empty
        if not img_queue.empty():
            img = img_queue.get()
            mask = blk_model.predict(img, rigor_rate)
            mask_queue.put(mask)


def pixel_model(cmd_queue: Queue, img_queue: Queue, mask_queue: Queue, pixel_model_path=pxl_model_path):
    pixel_model = PixelWisedDetector(os.path.join(ROOT_DIR, "models", pixel_model_path), blk_sz=1, channel_num=4)
    _ = pixel_model.predict(np.ones((nrows, ncols, nbands)))
    rigor_rate = 70
    while True:
        # deal with the cmd if cmd_queue is not empty
        if not cmd_queue.empty():
            cmd = cmd_queue.get()
            if isinstance(cmd, int):
                rigor_rate = cmd
            elif isinstance(cmd, str):
                if cmd == 'stop':
                    break
                else:
                    try:
                        pixel_model = PixelWisedDetector(os.path.join(ROOT_DIR, "models", pixel_model_path),
                                                         blk_sz=1, channel_num=4)
                    except Exception as e:
                        print(f"Load Model Failed! {e}")
        # deal with the img if img_queue is not empty
        if not img_queue.empty():
            img = img_queue.get()
            mask = pixel_model.predict(img, rigor_rate)
            mask_queue.put(mask)


if __name__ == '__main__':
    main()
