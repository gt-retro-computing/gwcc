from abi import ABI

"""
Stores ABI information for the LC-3.
"""
class LC3(ABI):
    CHAR_BITS = 16
    SHORT_BITS = 16
    INT_BITS = 16
    LONG_BITS = 0 # not (yet) supported
    PTR_BITS = 16

    CHAR_SIZE = 1
    SHORT_SIZE = 1
    INT_SIZE = 1
    LONG_SIZE = 2
    PTR_SIZE = 1
