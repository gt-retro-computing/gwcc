from .. import il

class ABI(object):
    CHAR_BITS = 0
    SHORT_BITS = 0
    INT_BITS = 0
    LONG_BITS = 0

    CHAR_SIZE = 0
    SHORT_SIZE = 0
    INT_SIZE = 0
    LONG_SIZE = 0

    @classmethod
    def bitsize(cls, il_type):
        if il_type == il.Types.char or il_type == il.Types.uchar:
            return cls.CHAR_BITS
        elif il_type == il.Types.short or il_type == il.Types.ushort:
            return cls.SHORT_BITS
        elif il_type == il.Types.int or il_type == il.Types.uint:
            return cls.INT_BITS
        elif il_type == il.Types.long or il_type == il.Types.ulong:
            return cls.LONG_BITS

    @classmethod
    def sizeof(cls, il_type):
        if il_type == il.Types.char or il_type == il.Types.uchar:
            return cls.CHAR_SIZE
        elif il_type == il.Types.short or il_type == il.Types.ushort:
            return cls.SHORT_SIZE
        elif il_type == il.Types.int or il_type == il.Types.uint:
            return cls.INT_SIZE
        elif il_type == il.Types.long or il_type == il.Types.ulong:
            return cls.LONG_SIZE
