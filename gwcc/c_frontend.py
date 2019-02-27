"""
The Gangweed Retargetable C compiler
This compiler brought to you by gangweed ganggang
"""

import sys

from pycparser import c_ast

import cfg
import il
from gwcc.exceptions import UnsupportedFeatureError
from gwcc.optimization.naturalization_pass import NaturalizationPass


class Scope(object):
    def __init__(self, name, height = 0, parent=None):
        self.symbols = {}
        self.types = {} # typedefs
        self.name = name
        self.height = height
        self.parent = parent

    def resolve_symbol(self, name):
        scope = self
        while scope:
            if name in scope.symbols:
                return scope, scope.symbols[name]
            scope = scope.parent
        return None, None

    def resolve_type(self, name):
        scope = self
        while scope:
            if name in scope.types:
                return scope.types[name]
            scope = scope.parent
        return None, None

    def resolve_basetype(self, name):
        type_decl = self.resolve_type(name)
        while type_decl:
            if type(type_decl) == c_ast.IdentifierType:
                return type_decl
            elif type(type_decl) == c_ast.Struct:
                return type_decl
            else:
                raise RuntimeError("don't know how to resolve type " + str(type_decl))
        return name

class Frontend(object):
    def __init__(self, arch):
        # target abi information
        self.target_arch = arch

        # state
        self._scope_stack = [Scope('global')]
        self._scope_cnt = 0
        self._c_variables = {}

        self.cur_pragma_loc = 0
        self.cur_pragma_linkage = 'C'

        self.cur_func = None
        self.cur_block = None
        self.loop_stack = None # stack of tuples (cond_block, end_block) for continue and break statements

        # output
        self._globals = []
        self._compiled = False

    def get_globals(self):
        if not self._compiled:
            raise RuntimeError('input has not been compiled yet')
        return self._globals

    @property
    def current_scope(self):
        return self._scope_stack[-1]

    @property
    def scope_depth(self):
        return len(self._scope_stack)

    def scope_push(self):
        SyntaxError
        scope_name = 'local_%s' % (self._scope_cnt,)
        self._scope_cnt += 1
        new_scope = Scope(scope_name, self.current_scope.height + 1, self.current_scope)
        self._scope_stack.append(new_scope)
        return new_scope

    def scope_pop(self, verify=None):
        if verify:
            assert self.current_scope == verify
        return self._scope_stack.pop()

    def on_compound_node(self, compound):
        """
        Descend into a block, pushing a new scope onto the scope stack, and compile all statements in the block.
        Afterwards, pop and discard the newly-made scope off from the scope stack.
        :param compound: instance of c_ast.Compound
        """
        assert type(compound) == c_ast.Compound
        new_scope = self.scope_push()
        if compound.block_items:
            self.compile_stmts(compound.block_items)
        self.scope_pop(new_scope)

    def on_typedef_node(self, node):
        assert type(node) == c_ast.Typedef
        typedef_name = node.name
        self.current_scope.types[typedef_name] = node.type.type

    def add_stmt(self, stmt):
        assert self.cur_func
        self.cur_block.add_stmt(stmt)
        if type(stmt) == il.GotoStmt:
            self.cur_func.cfg.add_edge(cfg.FlowEdge(self.cur_block, stmt.dst_block))
            self.cur_block = self.cur_func.cfg.new_block()
        elif type(stmt) == il.CondJumpStmt:
            self.cur_func.cfg.add_edge(cfg.FlowEdge(self.cur_block, stmt.true_block))
            self.cur_func.cfg.add_edge(cfg.FlowEdge(self.cur_block, stmt.false_block))
            self.cur_block = self.cur_func.cfg.new_block()
        elif type(stmt) == il.ReturnStmt:
            self.cur_block = self.cur_func.cfg.new_block()

    def on_decl_node(self, node):
        """
        :param node: c_ast.Decl node
        :return: new IL variable corresponding to the declaration
        """
        assert type(node) == c_ast.Decl
        decl_name = node.name
        if decl_name in self.current_scope.symbols:
            raise SyntaxError("redefinition of %s" % (decl_name,))
        else:
            self.current_scope.symbols[decl_name] = node

            var_type = self.get_node_type(node.type)
            if var_type == il.Types.ptr:
                ref_level, ref_type = self.extract_pointer_type(node.type)
                # print 'pointer declared: %s %d %s' % (node.name, ref_level, ref_type)
            else:
                # print 'local declared: %s' % (node.name,)
                ref_level, ref_type = 0, None

            var_name = '_' + str(self.current_scope.name) + '_' + node.name
            il_var = il.Variable(var_name, var_type, ref_level, ref_type)

            if self.scope_depth > 1: # we are in a function -> this is a local decl.
                if node.init:
                    init_expr_var = self.on_expr_node(node.init)
                    self.add_stmt(self.on_assign(il_var, init_expr_var))
                if self.cur_func:
                    self.cur_func.locals.append(il_var)
            else:
                init = None
                if node.init:
                    if type(node.init) == c_ast.Constant:
                        const_type, init = self.get_constant_value(node.init)
                    elif type(node.init) == c_ast.ID:
                        id_var = self.on_id_node(node.init)
                        for glob in self._globals:
                            if glob.name == node.init.name:
                                init = glob.init
                                break
                        else:
                            raise RuntimeError("couldn't find initialiser for referenced global " + node.init.name)
                    else:
                        raise UnsupportedFeatureError('global variable initialisers must be constant')
                self._globals.append(il.GlobalName(node.name, il_var, init, self.cur_pragma_loc, self.cur_pragma_linkage))
            self._c_variables[node] = il_var
            return il_var


    def duplicate_var(self, var):
        """
        Creates a new temporary with the same type, reflevel, and reftype as the one specified.
        """
        assert type(var) == il.Variable
        return self.cur_func.new_temporary(var.type, var.ref_level, var.ref_type)

    def on_assign(self, dst, src):
        assert type(dst) == il.Variable
        assert type(src) == il.Variable

        if dst.type != src.type:
            if dst.type == il.Types.ptr:
                assert dst.ref_level > 0
            return il.CastStmt(dst, src)
        else:
            assert dst.ref_level == src.ref_level
            assert dst.ref_type == src.ref_type
            return il.UnaryStmt(dst, il.UnaryOp.Identity, src)

    def on_funcdef_node(self, node):
        assert type(node) == c_ast.FuncDef
        func_decl = node.decl
        self.current_scope.symbols[func_decl.name] = func_decl

        # new scope
        new_scope = self.scope_push()
        self.loop_stack = []

        # return val
        retvar = il.Variable('_retval', self.get_node_type(func_decl.type.type.type))
        # process parameters
        argvars = []
        if func_decl.type.args:
            for param_decl in func_decl.type.args.params:
                argvars.append(self.on_decl_node(param_decl))

        self.cur_func = il.Function(func_decl.name, argvars, retvar)
        self._globals.append(il.GlobalName(func_decl.name, self.cur_func, None, self.cur_pragma_loc))
        self._c_variables[func_decl] = self.cur_func
        self.cur_block = self.cur_func.cfg.new_block()

        # process body
        self.on_compound_node(node.body)
        self.add_stmt(il.ConstantStmt(self.cur_func.retval, il.Constant(self.make_int_constant(0), self.cur_func.retval.type)))
        self.add_stmt(il.ReturnStmt()) # in case of missing return
        self.cur_func.verify() # integrity check coz i am stupid

        NaturalizationPass(self.cur_func).process()
        self.cur_func.verify() # integrity check coz i am stupid

        # exit scope
        self.scope_pop(new_scope)
        self.cur_func = None
        self.cur_block = None
        self.loop_stack = None

    def on_if_node(self, node):
        assert type(node) == c_ast.If

        # handle cond
        cond_val = self.on_expr_node(node.cond)

        # generate control flow
        true_block = self.cur_func.cfg.new_block()
        end_block = self.cur_func.cfg.new_block()
        if node.iffalse:
            false_block = self.cur_func.cfg.new_block()
        else:
            false_block = end_block
        self.add_stmt(il.CondJumpStmt(true_block, false_block, cond_val, il.ComparisonOp.Neq,
                                      il.Constant(Frontend.make_int_constant(0), cond_val.type)))

        # handle iftrue
        self.cur_block = true_block
        self.on_stmt_node(node.iftrue)
        self.add_stmt(il.GotoStmt(end_block))

        # handle iffalse
        if node.iffalse:
            self.cur_block = false_block
            self.on_stmt_node(node.iffalse)
            self.add_stmt(il.GotoStmt(end_block))

        self.cur_block = end_block

    def on_return_node(self, node):
        assert type(node) == c_ast.Return
        assert self.cur_func.retval
        retval = self.on_expr_node(node.expr)
        self.add_stmt(self.on_assign(self.cur_func.retval, retval))
        self.add_stmt(il.ReturnStmt())

        self.cur_block = self.cur_func.cfg.new_block()

    def on_binary_op_node(self, node):
        srcA = self.on_expr_node(node.left)
        srcB = self.on_expr_node(node.right)
        il_op = Frontend.parse_binary_op(node.op)
        return self.on_binary_op(srcA, srcB, il_op)

    @staticmethod
    def parse_binary_op(op):
        if op == '+':
            return il.BinaryOp.Add
        elif op == '-':
            return il.BinaryOp.Sub
        elif op == '*':
            return il.BinaryOp.Mul
        elif op == '==':
            return il.BinaryOp.Equ
        elif op == '!=':
            return il.BinaryOp.Neq
        elif op == '<':
            return il.BinaryOp.Lt
        elif op == '>':
            return il.BinaryOp.Gt
        elif op == '&&':
            return il.BinaryOp.LogicalAnd
        elif op == '||':
            return il.BinaryOp.LogicalOr
        elif op == '&':
            return il.BinaryOp.And
        elif op == '|':
            return il.BinaryOp.Or
        elif op == '*':
            return il.BinaryOp.Mul
        else:
            raise UnsupportedFeatureError('unsupported binary operation ' + op)

    def on_binary_op(self, srcA, srcB, il_op):
        assert type(srcA) == il.Variable
        assert type(srcB) == il.Variable
        assert il_op.parent == il.BinaryOp

        a_type, b_type = srcA.type, srcB.type
        if srcA.type == srcB.type:
            srcA_casted = srcA
            srcB_casted = srcB
        elif il.Types.is_less_than(a_type, b_type):
            srcA_casted = self.duplicate_var(srcB)
            cast_stmt = self.on_assign(srcA_casted, srcA)
            self.add_stmt(cast_stmt)
            srcB_casted = srcB
        elif il.Types.is_less_than(b_type, a_type):
            srcA_casted = srcA
            srcB_casted = self.duplicate_var(srcA)
            cast_stmt = self.on_assign(srcB_casted, srcB)
            self.add_stmt(cast_stmt)
        else:
            assert False # wtf

        new_var = self.duplicate_var(srcA_casted)
        new_stmt = il.BinaryStmt(new_var, il_op, srcA_casted, srcB_casted)
        self.add_stmt(new_stmt)
        return new_var

    def on_dereference(self, ptr_var):
        assert type(ptr_var) == il.Variable
        assert ptr_var.ref_level > 0
        if ptr_var.ref_level > 1:
            dst_var = self.cur_func.new_temporary(il.Types.ptr, ptr_var.ref_level - 1, ptr_var.ref_type)
        else:
            dst_var = self.cur_func.new_temporary(ptr_var.ref_type, 0, None)
        self.add_stmt(il.DerefReadStmt(dst_var, ptr_var))
        return dst_var

    def on_reference(self, var):
        assert type(var) == il.Variable
        ref_type = var.type if var.ref_level == 0 else var.ref_type
        dst_var = self.cur_func.new_temporary(il.Types.ptr, var.ref_level + 1, ref_type)
        self.add_stmt(il.RefStmt(dst_var, var))
        return dst_var

    def on_assign_node(self, node): # assignment EXRESSION
        is_ptr = type(node.lvalue) == c_ast.UnaryOp and node.lvalue.op == '*'
        is_array = type(node.lvalue) == c_ast.ArrayRef

        # lhs should be evaluated first
        if is_ptr:
            lhs = self.on_expr_node(node.lvalue.expr)
        elif is_array:
            lhs = self.on_array_ref_node_ptr(node.lvalue)
            is_ptr = True
        else:
            lhs = self.on_expr_node(node.lvalue)
        if type(node.lvalue) != c_ast.ID and not is_ptr:
            raise RuntimeError('unsupported lvalue ' + str(node.lvalue))

        # now evaluate rhs
        rhs_value = self.on_expr_node(node.rvalue)
        if node.op != '=': # examples are like +=, ^=, >>=, etc.
            op = Frontend.parse_binary_op(node.op[:-1])
            lhs_value = self.on_dereference(lhs) if is_ptr else lhs
            rhs_value = self.on_binary_op(lhs_value, rhs_value, op)

        if is_ptr:
            self.add_stmt(il.DerefWriteStmt(lhs, rhs_value))
        else:
            self.add_stmt(self.on_assign(lhs, rhs_value))

        # rhs_value is a variable which holds the newly-stored value
        assert type(rhs_value) == il.Variable
        return rhs_value

    def on_while(self, node):
        assert type(node) == c_ast.While

        cond_block = self.cur_func.cfg.new_block() # block holding loop conditional
        stmt_block = self.cur_func.cfg.new_block() # block holding loop body
        end_block = self.cur_func.cfg.new_block() # next block after loop
        self.add_stmt(il.GotoStmt(cond_block))

        # handle cond
        self.cur_block = cond_block
        cond_var = self.on_expr_node(node.cond)
        self.add_stmt(il.CondJumpStmt(stmt_block, end_block, cond_var, il.ComparisonOp.Neq,
                                      il.Constant(Frontend.make_int_constant(0), cond_var.type)))

        # handle stmt
        self.cur_block = stmt_block
        self.loop_stack.append((cond_block, end_block))
        self.on_stmt_node(node.stmt)
        self.add_stmt(il.GotoStmt(cond_block))

        self.loop_stack.pop()
        self.cur_block = end_block

    def on_pragma_node(self, node):
        pragma = node.string
        parts = pragma.split(' ')
        if parts[0] == 'location':
            try:
                loc = int(parts[1], 0)
            except ValueError:
                raise SyntaxError('invalid pragma location: ' + parts[1])
            self.cur_pragma_loc = loc
        elif parts[0] == 'extern':
            if len(parts) != 2:
                raise SyntaxError('invalid linkage pragma: ' + node.string)
            self.cur_pragma_linkage = parts[1]
        else:
            sys.stderr.write('warning: ignored pragma ' + pragma + '\n')

    # nodes that do not evaluate
    def on_stmt_node(self, node):
        typ = type(node)
        if typ == c_ast.Pragma:
            self.on_pragma_node(node)
        elif typ == c_ast.Typedef:
            self.on_typedef_node(node)
        elif typ == c_ast.Decl:
            self.on_decl_node(node)
        elif typ == c_ast.FuncDef:
            self.on_funcdef_node(node)
        elif typ == c_ast.If:
            self.on_if_node(node)
        elif typ == c_ast.Return:
            self.on_return_node(node)
        elif typ == c_ast.Compound:
            self.on_compound_node(node)
        elif typ == c_ast.EmptyStatement:
            pass
        elif typ == c_ast.While:
            self.on_while(node)
        elif typ == c_ast.Continue:
            self.on_continue_node(node)
        elif typ == c_ast.Break:
            self.on_break_node(node)
        # elif typ == c_ast.For:
        #     self.on_for(node)
        else:
            self.on_expr_node(node)

    def on_continue_node(self, node):
        assert type(node) == c_ast.Continue

        if not self.cur_func:
            raise SyntaxError("use of 'continue' outside of function")
        if not self.loop_stack:
            raise SyntaxError("use of 'continue' outside of loop")
        start_block, end_block = self.loop_stack[-1]
        self.add_stmt(il.GotoStmt(start_block))
        self.cur_block = self.cur_func.cfg.new_block()


    def on_break_node(self, node):
        assert type(node) == c_ast.Break

        if not self.cur_func:
            raise SyntaxError("use of 'break' outside of function")
        if not self.loop_stack:
            raise SyntaxError("use of 'break' outside of loop")
        start_block, end_block = self.loop_stack[-1]
        self.add_stmt(il.GotoStmt(end_block))
        self.cur_block = self.cur_func.cfg.new_block()

    def on_constant(self, const_type, value):
        assert type(value) == il.CompiledValue
        il_var = self.cur_func.new_temporary(const_type, 0, None)
        assign_stmt = il.ConstantStmt(il_var, il.Constant(value, const_type))
        self.add_stmt(assign_stmt)
        return il_var

    def on_constant_node(self, node):
        const_type, value = self.get_constant_value(node)
        return self.on_constant(const_type, value)


    @staticmethod
    def make_int_constant(value):
        return il.CompiledValue(value, il.CompiledValueType.Integer)

    @staticmethod
    def make_pointer_constant(value):
        return il.CompiledValue(value, il.CompiledValueType.Pointer)

    def get_constant_value(self, node):
        if node.type == 'int':
            return il.Types.int, Frontend.make_int_constant(int(node.value, 0))
        elif node.type == 'string':
            assert type(node.value) == str
            if node.value[0] != '"' or node.value[-1] != '"':
                raise SyntaxError('invalid char constant ' + node.value)
            str_value = node.value[1:-1] + '\0'
            value_escaped = ''.join(c for c in str_value if c.isalnum())
            var_name = '__A_' + value_escaped
            il_var = il.Variable(var_name, il.Types.char)
            string_init = il.CompiledValue(map(ord, str_value), il.CompiledValueType.WordArray)
            self._globals.append(il.GlobalName(var_name, il_var, string_init, self.cur_pragma_loc, self.cur_pragma_linkage))
            return il.Types.ptr, Frontend.make_pointer_constant(var_name)
        elif node.type == 'char':
            if node.value[0] != "'" or node.value[-1] != "'":
                raise SyntaxError('invalid char constant ' + node.value)
            return il.Types.char, Frontend.make_int_constant(ord(str(node.value[1:-1]).decode('string-escape')))
        else:
            raise UnsupportedFeatureError('unsupported constant type ' + node.type)

    def on_postincrement_node(self, expr_node):
        expr_var = self.on_expr_node(expr_node) # lol, this will result in a blatant common subexpression
        tmp_var = self.duplicate_var(expr_var) # this extra copy here is required in case expr_node is a local
        self.add_stmt(self.on_assign(tmp_var, expr_var))
        self.on_preincrement_node(expr_node)
        return tmp_var

    def on_preincrement_node(self, expr_node):
        # this is kinda hacky but w/e
        return self.on_assign_node(c_ast.Assignment('+=', expr_node, c_ast.Constant('int', '1')))

    def on_postdecrement_node(self, expr_node):
        expr_var = self.on_expr_node(expr_node)
        self.on_predecrement_node(expr_node)
        return expr_var

    def on_predecrement_node(self, expr_node):
        return self.on_assign_node(c_ast.Assignment('-=', expr_node, c_ast.Constant('int', '1')))

    def on_sizeof_node(self, sizeof_node):
        typ = self.get_node_type(sizeof_node.type)
        type_size = self.target_arch.sizeof(typ)
        return self.on_constant(il.Types.int, Frontend.make_int_constant(type_size))

    def on_unary_op_node(self, node):
        if node.op == 'p++':
            return self.on_postincrement_node(node.expr)
        elif node.op == '++':
            return self.on_preincrement_node(node.expr)
        elif node.op == 'p--':
            return self.on_postdecrement_node(node.expr)
        elif node.op == '--':
            return self.on_predecrement_node(node.expr)
        elif node.op == 'sizeof':
            return self.on_sizeof_node(node.expr)

        expr_var = self.on_expr_node(node.expr)
        if node.op == '*':
            return self.on_dereference(expr_var)
        elif node.op == '&':
            return self.on_reference(expr_var)
        else:
            il_op = Frontend.parse_unary_op(node.op)
            dst_var = self.duplicate_var(expr_var)
            new_stmt = il.UnaryStmt(dst_var, il_op, expr_var)
            self.add_stmt(new_stmt)
            return dst_var

    @staticmethod
    def parse_unary_op(op):
        if op == '!':
            return il.UnaryOp.LogicalNot
        elif op == '-':
            return il.UnaryOp.Minus
        elif op == '~':
            return il.UnaryOp.Negate
        else:
            raise UnsupportedFeatureError('unsupported unary operation ' + op)

    def on_id_node(self, node):
        """Resolve an identifier (ID) node into a variable"""
        scope, ast_decl = self.current_scope.resolve_symbol(node.name)
        if not scope:
            raise SyntaxError('use of undeclared symbol ' + node.name)
        il_var = self._c_variables[ast_decl]
        return il_var

    def on_array_ref_node_ptr(self, node):
        # base
        base_var = self.on_expr_node(node.name)
        # subscript
        subscript_var = self.on_expr_node(node.subscript)
        ptr_var = self.on_binary_op(base_var, subscript_var, il.BinaryOp.Add)
        return ptr_var

    def on_array_ref_node(self, node):
        ptr_var = self.on_array_ref_node_ptr(node)
        val_var = self.on_dereference(ptr_var)
        return val_var

    def on_cast_node(self, node):
        print node
        to_type = self.get_node_type(node.to_type.type)
        if to_type == il.Types.ptr:
            ref_level, ref_type = self.extract_pointer_type(node.to_type.type)
        else:
            ref_level, ref_type = 0, None
        dst_var = self.cur_func.new_temporary(to_type, ref_level, ref_type)
        expr_var = self.on_expr_node(node.expr)
        self.add_stmt(il.CastStmt(dst_var, expr_var))
        return dst_var

    def on_func_call_node(self, node):
        num_args = 0
        for arg in node.args:
            arg_var = self.on_expr_node(arg)
            self.add_stmt(il.ParamStmt(arg_var))
            num_args += 1
        func_expr = self.on_expr_node(node.name)
        if type(func_expr) == il.Function:
            # also FIXME
            func_expr = self.on_constant(il.Types.ptr, il.CompiledValue(func_expr.name, il.CompiledValueType.Pointer))
        dst_var = self.cur_func.new_temporary(il.Types.int, 0, None)# hack lol FIXME
        self.add_stmt(il.CallStmt(dst_var, func_expr, num_args))
        return dst_var

    # nodes that evaluate. return an ILVariable holding the evaluated value
    def on_expr_node(self, node):
        typ = type(node)
        if typ == c_ast.Assignment:
            return self.on_assign_node(node)
        elif typ == c_ast.BinaryOp:
            return self.on_binary_op_node(node)
        elif typ == c_ast.ID:
            return self.on_id_node(node)
        elif typ == c_ast.Constant:
            return self.on_constant_node(node)
        elif typ == c_ast.UnaryOp:
            return self.on_unary_op_node(node)
        elif typ == c_ast.ArrayRef:
            return self.on_array_ref_node(node)
        elif typ == c_ast.Cast:
            return self.on_cast_node(node)
        elif typ == c_ast.FuncCall:
            return self.on_func_call_node(node)
        else:
            raise UnsupportedFeatureError("unsupported ast expr node " + str(node))

    def compile_stmts(self, stmts):
        for node in stmts:
            if self.cur_func:
                from pycparser import c_generator
                generator = c_generator.CGenerator()
                self.add_stmt(il.CommentStmt(generator.visit(node).split('\n')[0]))
            self.on_stmt_node(node)

    def compile(self, ast):
        self.compile_stmts(ast.ext)
        self._compiled = True

    @staticmethod
    def interpret_identifier_type(names):
        # todo: warn on default-int, repeat short/signed/unsigned specifier, etc.
        def error_specifier(token, spec):
            raise SyntaxError("cannot combine '%s' with previous declaration specifier %s" % (token, spec))

        decl_sign = ''
        decl_size = ''
        decl_type = ''
        for token in names:
            if token == 'unsigned':
                if decl_sign == 'signed':
                    error_specifier(token, decl_sign)
                decl_sign = 'unsigned'
            elif token == 'signed':
                if decl_sign == 'unsigned':
                    error_specifier(token, decl_sign)
                decl_sign = 'signed'
            elif token == 'short':
                if 'long' in decl_size:
                    error_specifier(token, decl_size)
                decl_size = 'short'
            elif token == 'long':
                if decl_size == 'short':
                    error_specifier(token, decl_size)
                decl_size += token
            else:
                if decl_type:
                    error_specifier(token, decl_type)
                decl_type = token

        if not decl_type:
            decl_type = 'int'
        if decl_size:
            if decl_type != 'int':
                error_specifier(decl_size, decl_type)
        if not decl_sign and decl_type in ['int', 'char']:
            decl_sign = 'signed'
        elif decl_sign and decl_type not in ['int', 'char']:
                error_specifier(decl_sign, decl_type)

        return decl_sign, decl_size, decl_type

    @staticmethod
    def parse_decl_type(signedness, decl_size, decl_type):
        unsigned = signedness == 'unsigned'
        if decl_type == 'char':
            return il.Types.uchar if unsigned else il.Types.char
        elif decl_type == 'int':
            if decl_size == 'short':
                return il.Types.ushort if unsigned else il.Types.short
            elif decl_size == 'long':
                return il.Types.ulong if unsigned else il.Types.long
            elif decl_size == 'longlong':
                return il.Types.ulonglong if unsigned else il.Types.longlong
            else:
                return il.Types.uint if unsigned else il.Types.int
        elif decl_type == 'void':
            return il.Types.void
        elif decl_type == 'float':
            return il.Types.float
        elif decl_type == 'double':
            if decl_size == 'long':
                return il.Types.longdouble
            else:
                return il.Types.double
        else:
            return None

    def get_node_type(self, node):
        if type(node) == c_ast.TypeDecl:
            return self.get_node_type(node.type)
        if type(node) == c_ast.IdentifierType:
            signedness, decl_size, decl_type = Frontend.interpret_identifier_type(node.names)
            builtin_type = Frontend.parse_decl_type(signedness, decl_size, decl_type)
            if builtin_type:
                return builtin_type
            else:
                # try to resolve
                return self.get_node_type(self.current_scope.resolve_basetype(decl_type))
        elif type(node) == c_ast.PtrDecl:
            return il.Types.ptr
        else:
            raise RuntimeError("unsupported ast type decl " + str(node))

    def extract_pointer_type(self, node):
        """
        Extracts reflevel and reftype from a PtrDecl ast node.
        :param node: PtrDecl node
        :return: reference level (i.e. pointer, pointer to pointer, etc.) and pointed-to type
        """
        assert type(node) == c_ast.PtrDecl
        ref_level = 0
        while type(node) == c_ast.PtrDecl:
            node = node.type
            ref_level += 1
        ref_type = self.get_node_type(node)
        return ref_level, ref_type
