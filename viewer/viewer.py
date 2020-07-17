import sys
import time

import argparse
import PIL.ImageTk
import PIL.Image
import tkinter
import threading

import GT521F32

from typing import Tuple, ClassVar


class GT521F32Viewer(object):
    _FRAME_RATE: ClassVar[int] = 24
    _DIMENSIONS: Tuple[int, int] = (
        160,
        120,
    )  # Might be better to retrieve this from reader

    _root: tkinter.Tk
    _image_panel: tkinter.Label
    _reader: GT521F32.GT521F32
    _scale_factor: int
    _stop: bool

    def __init__(self, reader: GT521F32.GT521F32, scale_factor: int = 1):
        self._reader = reader
        self._scale_factor = scale_factor

        self._stop = False

        self._root = tkinter.Tk()
        self._image_panel = tkinter.Label(self._root)
        self._image_panel.pack(padx=0, pady=0)

        self._root.title("GT521F32")
        self._root.geometry(
            "%dx%d" % tuple(_ * scale_factor for _ in GT521F32Viewer._DIMENSIONS)
        )
        self._root.resizable(0, 0)
        self._root.wm_protocol("WM_DELETE_WINDOW", self.stop)

    def _video_loop(self):
        data = self._reader._get_raw_image()
        if data:
            image = PIL.Image.frombytes("L", self._DIMENSIONS, data, "raw")
            self._update(image)

        if not self._stop:
            self._root.after(1_000 // GT521F32Viewer._FRAME_RATE, self._video_loop)

    def start(self):
        self._reader.set_led(True)
        self._root.after(1_000 // GT521F32Viewer._FRAME_RATE, self._video_loop)
        self._root.mainloop()

    def _update(self, image: PIL.ImageTk.PhotoImage):
        if self._scale_factor != 1:
            image = image.resize(
                (
                    int(image.width * self._scale_factor),
                    int(image.height * self._scale_factor),
                )
            )
        # To avoid undue GC
        self._image_tk = PIL.ImageTk.PhotoImage(image)
        self._image_panel.config(image=self._image_tk)

    def stop(self):
        self._stop = True
        self._reader.set_led(False)
        self._root.quit()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-d", "--device", required=True, help="Path to GT521F32 device")
    parser.add_argument(
        "-f", "--scale_factor", type=int, default=1.5, help="Image scaling factor."
    )
    args = parser.parse_args()

    try:
        v = GT521F32Viewer(GT521F32.GT521F32(args.device), args.scale_factor)
        v.start()
    except GT521F32.GT521F32Exception:
        print("Could not open fingerprint device.")
    except (KeyboardInterrupt, InterruptedError):
        v.stop()
