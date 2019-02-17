"""
A simple 3-address code IL for compiling C code.
"""

from enum import Enum
from cfg import ControlFlowGraph, BasicBlock

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

class ConstantStmt(object):
    def __init__(self, dst, imm):
        assert type(dst) == Variable
        if dst.type != imm.type:
            raise ValueError('Constant load statement operands must be of equal type')
        self.dst = dst
        self.imm = imm

    def __repr__(self):
        return '%s = %s' % (self.dst, self.imm)

class UnaryStmt(object):
    def __init__(self, dst, op, src):
        assert type(dst) == Variable
        assert op.parent == UnaryOp
        assert type(src) == Variable
        if dst.type != src.type:
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

class GotoStmt(object):
    def __init__(self, dst_block):
        assert type(dst_block) == BasicBlock
        self.dst_block = dst_block

    def __repr__(self):
        return 'goto %s' % (self.dst_block,)

class ComparisonOp(Enum):
    Equ = '=='
    Neq = '!='
    Lt = '<'
    Gt = '>'
    Leq = '<='
    Geq = '>='

class CondJumpStmt(object):
    def __init__(self, true_block, false_block, srcA, op, imm):
        assert type(true_block) == BasicBlock
        assert type(false_block) == BasicBlock
        assert type(srcA) == Variable
        assert op.parent == ComparisonOp
        assert type(imm) == Constant
        if srcA.type != imm.type:
            raise ValueError('Conditional jump statement operands must be of equal type')
        self.true_block = true_block
        self.false_block = false_block
        self.srcA = srcA
        self.op = op
        self.imm = imm

    def __repr__(self):
        return 'if (%s %s %s) goto %s else goto %s' % (self.srcA, self.op, self.imm, self.true_block, self.false_block)

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

        self.cfg = ControlFlowGraph()

    @property
    def num_args(self):
        return len(self.params)

    def new_temporary(self, typ, ref_level, ref_type):
        name = 't' + str(len(self.temporaries))
        il_var = Variable(name, typ, ref_level, ref_type)
        self.temporaries[il_var] = il_var
        return il_var

    def verify(self):
        # ensure that all jumps reference valid basicblocks
        for bb in self.cfg.basic_blocks:
            if not bb.stmts:
                continue

            control_flow_stmts = [GotoStmt, CondJumpStmt, ReturnStmt]
            for i in range(len(bb.stmts) - 1):
                assert type(bb.stmts[i]) not in control_flow_stmts

            last_stmt = bb.stmts[-1]
            assert type(last_stmt) in control_flow_stmts
            if type(last_stmt) == GotoStmt:
                assert last_stmt.dst_block in self.cfg.basic_blocks
                assert len(self.cfg.get_edges(bb)) == 1
                assert next(iter(self.cfg.get_edges(bb))).dst == last_stmt.dst_block
            elif type(last_stmt) == CondJumpStmt:
                assert last_stmt.true_block in self.cfg.basic_blocks
                assert last_stmt.false_block in self.cfg.basic_blocks
                if last_stmt.true_block != last_stmt.false_block:
                    assert len(self.cfg.get_edges(bb)) == 2
                else:
                    assert len(self.cfg.get_edges(bb)) == 1
                dsts = map(lambda e: e.dst, self.cfg.get_edges(bb))
                assert last_stmt.true_block in dsts and last_stmt.false_block in dsts
            elif type(last_stmt) == ReturnStmt:
                assert len(self.cfg.get_edges(bb)) == 0

        # todo: verify def/use chains are valid

    def __str__(self):
        result = 'Function %s(%s) -> %s\n' % (self.name, ', '.join(map(str, self.params)), self.retval)
        result += self.cfg.pretty_print()
        return result
