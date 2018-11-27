
def int32_to_bytes(i32_number):
    ret_bytes = bytearray()
    for i in range(4):
        ret_bytes.append(i32_number % 256)

        i32_number //= 256
        pass
    return ret_bytes


def bytes_to_int32(bytes):
    ret = 0
    for i in range(4):
        ret *= 256
        ret += bytes[3 - i]
    return ret


class StpPacket:
    def __init__(self):
        self.sequenceNum = 0  # 4bytes
        self.ackNum = 0  # 4bytes

        # All flags take 1 byte
        self.isAck = False
        self.isSyn = False
        self.isRst = False
        self.isFin = False
        self.isValid = True

        self.data = None

    def build_flag(self):
        flag = 0
        if self.isAck:
            flag |= 1 << 0
        if self.isSyn:
            flag |= 1 << 1
        if self.isRst:
            flag |= 1 << 2
        if self.isFin:
            flag |= 1 << 3
        return flag

    def to_byte_array(self):
        ret_bytes = bytearray()
        ret_bytes += int32_to_bytes(self.sequenceNum)
        ret_bytes += int32_to_bytes(self.ackNum)

        flag = self.build_flag()
        ret_bytes.append(flag)

        # Append 1 byte checksum
        checksum_sum = 0
        for b in ret_bytes:
            checksum_sum += b
            checksum_sum %= 0x100
        if self.data is not None:
            for b in self.data:
                checksum_sum += b
                checksum_sum %= 0x100
        checksum = 0xff - checksum_sum  # Byte not
        ret_bytes.append(checksum)

        if self.data is not None:
            ret_bytes += self.data
        return ret_bytes

    def from_byte_array(self, bytes):
        self.sequenceNum = bytes_to_int32(bytes[0:4])
        self.ackNum = bytes_to_int32(bytes[4:8])

        flag = bytes[8]
        self.isAck = (flag & 1) == 1
        self.isSyn = ((flag >> 1) & 1) == 1
        self.isRst = ((flag >> 2) & 1) == 1
        self.isFin = ((flag >> 3) & 1) == 1

        self.data = bytes[10:]

        checksum_sum = 0
        for b in bytes:
            checksum_sum += b
            checksum_sum %= 0x100

        self.isValid = checksum_sum == 0xFF


