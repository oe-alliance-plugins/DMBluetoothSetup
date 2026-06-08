from enigma import IrProtocol, IrKey

from ..InputDeviceIRDatabase import irdb

class RC5:
    # {36k,msb,889}<1,-1|-1,1>(1,~F:1:6,T:1,D:5,F:6,^114m)+

    @staticmethod
    def build(definition):
        def reverseBits(n, count):
            result = 0
            for i in range(count):
                result <<= 1
                result |= n & 1
                n >>= 1
            return result

        keys = []
        for key, cmd in definition["keys"].items():
            keycode = irdb.mapKey(key)
            if not keycode:
                continue
            device = reverseBits(definition["device"] & 0x1F, 5)
            cmd = reverseBits(cmd & 0x3f, 6)
            make_msg = 0 | device << 1 | cmd << 6 #start and togglebit are handled by the integrated RC5 protocol
            make_len = 12
            key = IrKey(keycode, IrProtocol.IR_PROTO_RC5, make_msg, make_len, 0, 0)
            keys.append(key)
        return [(None, False, keys)]
