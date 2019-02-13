"""
A simple 3-address code IL for compiling C code.
"""

from enum import Enum

class ILTypes(Enum):
    char = 0
    uchar = 1
    short = 2
    ushort = 3
    int = 4
    uint = 5
    long = 6
    ulong = 7
    ptr = 1000
    void = 1001

    @staticmethod
    def is_unsigned(typ):
        return (typ.value % 1 != 0) and typ.value < ILTypes.ptr.value

    @staticmethod
    def is_less_than(a, b):
        assert a.value != ILTypes.ptr and a.value != ILTypes.void
        assert b.value != ILTypes.ptr and b.value != ILTypes.void
        return a.value < b.value

    @staticmethod
    def can_hold(a, b):
        """
        :param a: variable's type
        :param b: value's type
        :return: Return true if a variable of type can hold any value of type b.
        """
        assert a.value != ILTypes.ptr and a.value != ILTypes.void
        assert b.value != ILTypes.ptr and b.value != ILTypes.void
        return a.value >= b.value

class ILVariable(object):
    def __init__(self, name, typ):
        self.name = name
        self.type = typ

    def __repr__(self):
        return '%s<%s>' % (self.name, self.type)

class ILConstant(object):
    def __init__(self, value, typ):
        self.value = value
        self.type = typ

class ILBinaryOp(Enum):
    Add = '+'
    Sub = '-'
    And = '&'
    Or  = '|'
    Xor = '^'
    Shl = '<<'
    Shr = '>>'
    LogicalAnd = '&&'
    LogicalOr = '||'
    Mul = '*'
    Div = '/'
    Rem = '%'
    Equ = '=='
    Neq = '!='
    Lt = '<'
    Gt = '>'
    Leq = '<='
    Geq = '>='

class ILBinaryStmt(object):
    def __init__(self, dst, op, srcA, srcB):
        assert type(dst) == ILVariable
        assert type(srcA) == ILVariable
        assert type(srcB) == ILVariable
        if dst.type != srcA.type or dst.type != srcB.type:
            raise ValueError('Binary statement operands must be of equal type')

        self.dst = dst
        self.op = op
        self.srcA = srcA
        self.srcB = srcB

    def __repr__(self):
        return '%s = %s %s %s' % (self.dst, self.srcA, self.op, self.srcB)

class ILUnaryOp(Enum):
    Identity = ''
    Not = '!'
    Negate = '~'
    Minus = '-'

class ILUnaryStmt(object):
    def __init__(self, dst, op, src):
        assert type(dst) == ILVariable
        assert type(src) == ILVariable
        if dst.type != src.type:
            print dst.type
            print src.type
            raise ValueError('Unary statement operands must be of equal type')
        self.dst = dst
        self.op = op
        self.src = src

    def __repr__(self):
        return '%s = %s%s' % (self.dst, self.op, self.src)

class ILCastStmt(object):
    def __init__(self, dst, src):
        assert type(dst) == ILVariable
        assert type(src) == ILVariable
        self.dst = dst
        self.src = src

    def __repr__(self):
        return '%s = (%s) %s' % (self.dst, self.dst.type, self.src)

class ILLabel(object):
    def __init__(self, name):
        self.name = name
        self.idx = None

    def set_idx(self, index):
        self.idx = index

    def __repr__(self):
        return self.name

class ILGotoStmt(object):
    def __init__(self, label):
        assert type(label) == ILLabel
        self.label = label

    def __repr__(self):
        return 'goto %s' % (self.label,)

class ILComparisonOp(object):
    Equ = '=='
    Neq = '!='
    Lt = '<'
    Gt = '>'
    Leq = '<='
    Geq = '>='

class ILCondJump(object):
    def __init__(self, label, srcA, op, srcB):
        assert type(label) == ILLabel
        assert type(srcA) == ILVariable
        assert type(op) == ILComparisonOp
        assert type(srcB) == ILVariable
        if srcA.type != srcB.type:
            raise ValueError('Conditional jump statement operands must be of equal type')
        self.label = label
        self.srcA = srcA
        self.op = op
        self.srcB = srcB

    def __repr__(self):
        return 'if (%s %s %s) goto %s' % (self.srcA, self.op, self.srcB, self.label)

class ILParamStmt(object):
    def __init__(self, arg):
        assert type(arg) == ILVariable
        self.arg = arg

    def __repr__(self):
        return 'param %s' % (self.arg,)

class ILCallStmt(object):
    def __init__(self, func, nargs):
        assert type(func) == ILFunction
        assert type(nargs) == int
        self.func = func
        self.nargs = nargs

    def __repr__(self):
        return 'call %s, %d' % (self.func.name, self.nargs)

class IRReturnStmt(object):
    def __repr__(self):
        return 'return'

class ILRefStmt(object): # basically &x operator
    def __init__(self, dst, var):
        assert type(dst) == ILVariable
        assert type(var) == ILVariable
        self.dst = dst
        self.var = var

    def __repr__(self):
        return '%s = &%s' % (self.dst, self.var)

class ILDerefStmt(object): # basically *x operator
    def __init__(self, dst, ptr):
        assert type(dst) == ILVariable
        assert type(ptr) == ILVariable
        self.dst = dst
        self.ptr = ptr

    def __repr__(self):
        return '%s = *%s' % (self.dst, self.ptr)


class ILFunction(object):
    def __init__(self, name, params, retval):
        """
        :param name: name of the function
        :param params: an array of ILVariables representing the function's parameters
        :param retval: an ILVariable that represents the function's return value
        """

        self.name = name
        self.params = params
        self.retval = retval

        self.locals_size = 0
        self.locals = []

        self.stmts = []

    @property
    def num_args(self):
        return len(self.params)

    def add_stmt(self, stmt):
        self.stmts.append(stmt)
