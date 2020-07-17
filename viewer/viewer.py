import signal
import sys
import time
from PyQt5.QtCore import QThread, Qt, pyqtSignal, pyqtSlot
from PyQt5.QtWidgets import QApplication, QWidget, QLabel
from PyQt5.QtGui import QIcon, QPixmap, QImage

import threading
import PIL
import PIL.Image
from PIL.ImageQt import ImageQt

import GT521F32


class ViewerThread(QThread):
	set_image = pyqtSignal(QImage)
	_cancel: threading.Event

	def __init__(self, parent, reader):
		super().__init__(parent)
		self._reader = reader
		self._cancel = threading.Event()

	def run(self):
		with self._reader.led():
			while not self._cancel.is_set():
				time.sleep(1.0 / 25)  # 25 fps
				data = self._reader._get_raw_image()
				if data:
					img = PIL.Image.frombytes("L", (160, 120), data, "raw")
					self.set_image.emit(ImageQt(img))


class Viewer(QWidget):
	def __init__(self, reader):
		super().__init__()
		self._reader = reader
		self.left = 10
		self.top = 10
		self.width = 640
		self.height = 480
		self.initUI()

	def initUI(self):
		self.setWindowTitle("GT521F32")
		self.setGeometry(self.left, self.top, self.width, self.height)

		self._thread = ViewerThread(self, self._reader)
		self._thread.set_image.connect(self.set_image)

		self.label = QLabel(self)
		self.label.resize(160*3, 120*3)
		self.resize(160*3, 120*3)
		self._thread.start()
		self.show()

	@pyqtSlot(QImage)
	def set_image(self, img):
		self.label.setPixmap(QPixmap.fromImage(img).scaled(160*3, 120*3))

	def closeEvent(self, event):
		self._thread._cancel.set()
		self._thread.wait()
		event.accept()
		


def main():
	signal.signal(signal.SIGINT, signal.SIG_DFL) # Exit on Ctrl C
	app = QApplication(sys.argv)
	ex = Viewer(GT521F32.GT521F32(sys.argv[1]))
	ex.show()
	sys.exit(app.exec_())
