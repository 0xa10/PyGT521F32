import sgio

class SCSIInterface(object):
	def __init__(self, device_path):
		self._device_path = device_path
		
		self.is_open = False

	def open(self):
		try:
			self._file = open(self._device_path, "wb")
		except (FileNotFoundError, PermissionError) as e:
			raise SCSIException("Could not open drive - err %s." % (e,))

		self.is_open = True

	def read(self, size=1):
		assert size != 0
		# Allocate data 
		cdb = bytearray(0x10)
		cdb[0] = 0xEF
		cdb[1] = 0xFF # read
		data_in = bytearray(size)
		sgio.execute(self._file, cdb, None, data_in)

		return data_in

	def write(self, data):
		# Allocate data 
		cdb = bytearray(0x10)
		cdb[0] = 0xEF
		cdb[1] = 0xFE # write
		data_out = bytearray(data) 
		sgio.execute(self._file, cdb, data_out, None)

		return data_out

	def _close(self):
		self._file.close()

	def close(self):
		if self.is_open:
			self._close()
			self.is_open = False
