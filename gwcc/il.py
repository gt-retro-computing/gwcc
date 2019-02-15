"""
A simple 3-address code IL for compiling C code.
"""

from enum import Enum

class Types(Enum):
    char = 0
    uchar = 1
    short = 2
    ushort = 3
    int = 4
    uint = 5
    long = 6
    ulong = 7
    longlong = 8
    ulonglong = 9

    float = 100
    double = 101
    longdouble = 102

    ptr = 1000
    void = 1001

    @staticmethod
    def is_unsigned(typ):
        return (typ.value % 1 != 0) and typ.value < Types.float.value

    @staticmethod
    def is_less_than(a, b):
        assert a.value != Types.ptr and a.value != Types.void
        assert b.value != Types.ptr and b.value != Types.void
        return a.value < b.value

    @staticmethod
    def can_hold(a, b):
        """
        :param a: variable's type
        :param b: value's type
        :return: Return true if a variable of type can hold any value of type b.
        """
        assert a.value != Types.ptr and a.value != Types.void
        assert b.value != Types.ptr and b.value != Types.void
        return a.value >= b.value

class Variable(object):
    def __init__(self, name, typ, ref_level=0, ref_type=None):
        """
        :param name: variable name
        :param typ: variable type (il.Types instance)
        :param ref_level: reference level (e.g. int=0, int*=1, int**=2, etc.)
        :param ref_type: pointed type (e.g. int=None, int*=int, int**=int, etc.)
        """
        assert typ.parent == Types
        self.name = name
        self.type = typ
        # tbh, this is a hack for tracking variables at the generation stage, but w/e
        self.ref_level = ref_level
        self.ref_type = ref_type

        if ref_level == 0:
            assert ref_type is None
        else:
            assert ref_type.parent == Types

    def __repr__(self):
        if self.type == Types.ptr:
            return '%s%s.%s' % (self.ref_type, '*' * self.ref_level, self.name)
        else:
            return '%s.%s' % (self.type, self.name)

class Constant(object):
    def __init__(self, value, typ):
        assert typ.parent == Types
        self.value = value
        self.type = typ

    def __repr__(self):
        return '%s.%s' % (self.type, self.value)

class BinaryOp(Enum):
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

class BinaryStmt(object):
    def __init__(self, dst, op, srcA, srcB):
        assert type(dst) == Variable
        assert op.parent == BinaryOp
        assert type(srcA) == Variable
        assert type(srcB) == Variable
        if dst.type != srcA.type or dst.type != srcB.type:
            raise ValueError('Binary statement operands must be of equal type')

        self.dst = dst
        self.op = op
        self.srcA = srcA
        self.srcB = srcB

    def __repr__(self):
        return '%s = %s %s %s' % (self.dst, self.srcA, self.op, self.srcB)

class UnaryOp(Enum):
    Identity = ''
    Not = '!'
    Negate = '~'
    Minus = '-'

class UnaryStmt(object):
    def __init__(self, dst, op, src):
        assert type(dst) == Variable
        assert op.parent == UnaryOp
        assert type(src) == Variable or type(src) == Constant
        if dst.type != src.type:
            print dst.type
            print src.type
            raise ValueError('Unary statement operands must be of equal type')
        self.dst = dst
        self.op = op
        self.src = src

    def __repr__(self):
        return '%s = %s%s' % (self.dst, self.op, self.src)

class CastStmt(object):
    def __init__(self, dst, src):
        assert type(dst) == Variable
        assert type(src) == Variable
        self.dst = dst
        self.src = src

    def __repr__(self):
        return '%s = (%s) %s' % (self.dst, self.dst.type, self.src)

class Label(object):
    def __init__(self, name):
        self.name = name
        self._idx = None

    def __repr__(self):
        return self.name

class GotoStmt(object):
    def __init__(self, label):
        assert type(label) == Label
        self.label = label

    def __repr__(self):
        return 'goto %s' % (self.label,)

class ComparisonOp(Enum):
    Equ = '=='
    Neq = '!='
    Lt = '<'
    Gt = '>'
    Leq = '<='
    Geq = '>='

class CondJump(object):
    def __init__(self, label, srcA, op, imm):
        assert type(label) == Label
        assert type(srcA) == Variable
        assert op.parent == ComparisonOp
        assert type(imm) == Constant
        if srcA.type != imm.type:
            raise ValueError('Conditional jump statement operands must be of equal type')
        self.label = label
        self.srcA = srcA
        self.op = op
        self.imm = imm

    def __repr__(self):
        return 'if (%s %s %s) goto %s' % (self.srcA, self.op, self.imm, self.label)

class ParamStmt(object):
    def __init__(self, arg):
        assert type(arg) == Variable
        self.arg = arg

    def __repr__(self):
        return 'param %s' % (self.arg,)

class CallStmt(object):
    def __init__(self, func, nargs):
        assert type(func) == Function
        assert type(nargs) == int
        self.func = func
        self.nargs = nargs

    def __repr__(self):
        return 'call %s, %d' % (self.func.name, self.nargs)

class ReturnStmt(object):
    def __repr__(self):
        return 'return'

class RefStmt(object): # basically &x operator
    def __init__(self, dst, var):
        assert type(dst) == Variable
        assert type(var) == Variable
        self.dst = dst
        self.var = var

    def __repr__(self):
        return '%s = &%s' % (self.dst, self.var)

class DerefReadStmt(object): # basically *x operator
    def __init__(self, dst, ptr):
        assert type(dst) == Variable
        assert type(ptr) == Variable

        if dst.ref_level != ptr.ref_level - 1:
            raise ValueError('inconsistent reference levels %d and %d' % (dst.ref_level, ptr.ref_level))
        if dst.ref_level == 0 and dst.type != ptr.ref_type:
            raise ValueError('inconsistent dereferenced type')
        if dst.ref_level > 0 and dst.ref_type != ptr.ref_type:
            raise ValueError('inconsistent referenced type')
        self.dst = dst
        self.ptr = ptr

    def __repr__(self):
        return '%s = *%s' % (self.dst, self.ptr)

class DerefWriteStmt(object): # basically *x operator
    def __init__(self, ptr, dst):
        assert type(ptr) == Variable
        assert type(dst) == Variable

        if dst.ref_level != ptr.ref_level - 1:
            raise ValueError('inconsistent reference levels %d and %d' % (dst.ref_level, ptr.ref_level))
        if dst.ref_level == 0 and dst.type != ptr.ref_type:
            raise ValueError('inconsistent dereferenced type')
        if dst.ref_level > 0 and dst.ref_type != ptr.ref_type:
            raise ValueError('inconsistent referenced type')

        self.ptr = ptr
        self.dst = dst

    def __repr__(self):
        return '*%s = %s' % (self.ptr, self.dst)

class CommentStmt(object):
    """
    For debugging purposes.
    """
    def __init__(self, text):
        self.text = text

    def __repr__(self):
        return self.text

class Function(object):
    def __init__(self, name, params, retval):
        """
        :param name: name of the function
        :param params: an array of ILVariables representing the function's parameters
        :param retval: an ILVariable that represents the function's return value
        """

        self.name = name
        self.params = params
        self.retval = retval
        self.temporaries = {}

        self.locals_size = 0
        self.locals = []

        self.stmts = []
        self.labels = []

    @property
    def num_args(self):
        return len(self.params)

    def add_stmt(self, stmt):
        if type(stmt) == Label:
            raise ValueError('use place_label to add the label here, not add_stmt')
        self.stmts.append(stmt)

    def place_label(self, label):
        assert type(label) == Label
        label._idx = len(self.stmts)
        self.stmts.append(label)

    def new_label(self):
        label = Label('L%d' % (len(self.labels)))
        self.labels.append(label)
        return label

    def new_temporary(self, typ, ref_level, ref_type):
        name = 't' + str(len(self.temporaries))
        il_var = Variable(name, typ, ref_level, ref_type)
        self.temporaries[il_var] = il_var
        return il_var

    def verify(self):
        # ensure that all labels are placed
        for label in self.labels:
            assert label in self.stmts

        # ensure that all jumps reference valid labels
        for stmt in self.stmts:
            if type(stmt) == GotoStmt or type(stmt) == CondJump:
                assert stmt.label in self.labels

        # todo: verify def/use chains are valid
