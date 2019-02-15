"""
The Gangweed Retargetable C compiler
This compiler brought to you by gangweed ganggang
"""

from pycparser import c_ast
import il

class Scope(object):
    def __init__(self, height = 0, parent=None):
        self.symbols = {}
        self.types = {} # typedefs
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

class Compiler(object):
    def __init__(self, arch):
        self.scope_stack = [ Scope() ]
        self.target_arch = arch

        self.cur_func = None
        self.cur_func_c_locals = None # map from ast data to IRVariable
        self.loop_stack = None # stack of tuples (cond_label, end_label) for continue and break statements

    @property
    def current_scope(self):
        return self.scope_stack[-1]

    @property
    def current_scope_depth(self):
        return len(self.scope_stack)

    def scope_push(self):
        new_scope = Scope(self.current_scope.height + 1, self.current_scope)
        self.scope_stack.append(new_scope)
        return new_scope

    def scope_pop(self, verify=None):
        if verify:
            assert self.current_scope == verify
        return self.scope_stack.pop()

    def on_compound(self, compound):
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

    def on_typedef(self, node):
        assert type(node) == c_ast.Typedef
        typedef_name = node.name
        self.current_scope.types[typedef_name] = node.type.type

    def on_decl(self, node):
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

            if self.cur_func_c_locals is not None: # we are in a function -> this is a local decl.
                var_type = self.get_node_type(node.type)
                if var_type == il.Types.ptr:
                    ref_level, ref_type = self.extract_pointer_type(node.type)
                    print 'pointer declared: %s %d %s' % (node.name, ref_level, ref_type)
                else:
                    print 'local declared: %s' % (node.name,)
                    ref_level, ref_type = 0, None

                tmpvar_name = '_local_' + str(self.current_scope_depth) + '_' + node.name
                il_var = il.Variable(tmpvar_name, var_type, ref_level, ref_type)
                self.cur_func_c_locals[node] = il_var

                if node.init:
                    init_expr_var = self.on_expr(node.init)
                    self.cur_func.add_stmt(self.make_assign_stmt(il_var, init_expr_var))

                return il_var

    def duplicate_var(self, var):
        """
        Creates a new temporary with the same type, reflevel, and reftype as the one specified.
        """
        assert type(var) == il.Variable
        return self.cur_func.new_temporary(var.type, var.ref_level, var.ref_type)

    def make_assign_stmt(self, dst, src):
        assert type(dst) == il.Variable
        assert type(src) == il.Variable or type(src) == il.Constant

        if dst.type != src.type:
            # handle pointer arithmetic
            if dst.type == il.Types.ptr:
                assert dst.ref_level > 0
                ptr_size = self.target_arch.sizeof(dst.ref_type)
                if ptr_size > 1:
                    if type(src) == il.Variable:
                        src = self.on_binary_op(src, self.on_constant(src.type, ptr_size), il.BinaryOp.Mul)
                    elif type(src) == il.Constant:
                        src = self.on_constant(src.type, src.value * ptr_size)
                    else:
                        assert False
            return il.CastStmt(dst, src)
        else:
            if type(src) == il.Variable:
                assert dst.ref_level == src.ref_level
                assert dst.ref_type == src.ref_type
            else:
                assert dst.ref_level == 0
                assert dst.ref_type is None

            return il.UnaryStmt(dst, il.UnaryOp.Identity, src)

    def on_funcdef(self, node):
        assert type(node) == c_ast.FuncDef
        func_decl = node.decl
        self.current_scope.symbols[func_decl.name] = func_decl

        # new scope
        new_scope = self.scope_push()
        self.cur_func_c_locals = {}
        self.loop_stack = []

        # return val
        retvar = il.Variable('_retval', self.get_node_type(func_decl.type.type.type))
        # process parameters
        argvars = []
        for param_decl in func_decl.type.args.params:
            argvars.append(self.on_decl(param_decl))

        self.cur_func = il.Function(func_decl.name, argvars, retvar)

        # process body
        self.on_compound(node.body)
        print
        print '\n'.join(map(str,self.cur_func.stmts))
        self.cur_func.verify() # integrity check coz i am stupid

        # exit scope
        self.scope_pop(new_scope)
        self.cur_func = None
        self.cur_func_c_locals = None
        self.loop_stack = None

    def on_if(self, node):
        assert type(node) == c_ast.If

        # handle cond
        cond_val = self.on_expr(node.cond)
        true_branch_lbl = self.cur_func.new_label()
        end_lbl = self.cur_func.new_label()
        self.cur_func.add_stmt(il.CondJump(true_branch_lbl, cond_val, il.ComparisonOp.Neq, il.Constant(0, cond_val.type)))

        # handle iffalse
        if node.iffalse:
            self.on_stmt(node.iffalse)
        self.cur_func.add_stmt(il.GotoStmt(end_lbl))

        self.cur_func.place_label(true_branch_lbl)
        # handle iftrue
        self.on_stmt(node.iftrue)

        self.cur_func.place_label(end_lbl)

    def on_return(self, node):
        assert type(node) == c_ast.Return
        assert self.cur_func.retval
        retval = self.on_expr(node.expr)

        self.cur_func.add_stmt(self.make_assign_stmt(self.cur_func.retval, retval))

    def on_binary_op_node(self, node):
        srcA = self.on_expr(node.left)
        srcB = self.on_expr(node.right)
        il_op = Compiler.parse_binary_op(node.op)
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
        else:
            raise ValueError('unsupported binary operation ' + op)

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
            cast_stmt = self.make_assign_stmt(srcA_casted, srcA)
            self.cur_func.add_stmt(cast_stmt)
            srcB_casted = srcB
        elif il.Types.is_less_than(b_type, a_type):
            srcA_casted = srcA
            srcB_casted = self.duplicate_var(srcA)
            cast_stmt = self.make_assign_stmt(srcB_casted, srcB)
            self.cur_func.add_stmt(cast_stmt)
        else:
            assert False # wtf

        new_var = self.duplicate_var(srcA_casted)
        new_stmt = il.BinaryStmt(new_var, il_op, srcA_casted, srcB_casted)
        self.cur_func.add_stmt(new_stmt)
        return new_var

    def make_dereference(self, ptr_var):
        assert type(ptr_var) == il.Variable
        assert ptr_var.ref_level > 0
        if ptr_var.ref_level > 1:
            dst_var = self.cur_func.new_temporary(il.Types.ptr, ptr_var.ref_level - 1, ptr_var.ref_type)
        else:
            dst_var = self.cur_func.new_temporary(ptr_var.ref_type, 0, None)
        self.cur_func.add_stmt(il.DerefReadStmt(dst_var, ptr_var))
        return dst_var

    def make_reference(self, var):
        assert type(var) == il.Variable
        ref_type = var.type if var.ref_level == 0 else var.ref_type
        dst_var = self.cur_func.new_temporary(il.Types.ptr, var.ref_level + 1, ref_type)
        self.cur_func.add_stmt(il.RefStmt(dst_var, var))
        return dst_var

    def on_assign(self, node): # assignment EXRESSION
        is_ptr = type(node.lvalue) == c_ast.UnaryOp and node.lvalue.op == '*'

        # lhs should be evaluated first
        lhs = self.on_expr(node.lvalue.expr if is_ptr else node.lvalue)
        if type(node.lvalue) != c_ast.ID and not is_ptr:
            raise RuntimeError('unsupported lvalue ' + str(node))

        # now evaluate rhs
        rhs_value = self.on_expr(node.rvalue)
        if node.op != '=': # examples are like +=, ^=, >>=, etc.
            op = Compiler.parse_binary_op(node.op[:-1])
            lhs_value = self.make_dereference(lhs) if is_ptr else lhs
            rhs_value = self.on_binary_op(lhs_value, rhs_value, op)

        if is_ptr:
            self.cur_func.add_stmt(il.DerefWriteStmt(lhs, rhs_value))
        else:
            self.cur_func.add_stmt(self.make_assign_stmt(lhs, rhs_value))

        # rhs_value is a variable which holds the newly-stored value
        assert type(rhs_value) == il.Variable
        return rhs_value

    def on_while(self, node):
        assert type(node) == c_ast.While

        start_lbl = self.cur_func.new_label()
        end_lbl = self.cur_func.new_label()
        self.loop_stack.append((start_lbl, end_lbl))
        self.cur_func.place_label(start_lbl)

        # handle cond
        cond_var = self.on_expr(node.cond)
        self.cur_func.add_stmt(il.CondJump(end_lbl, cond_var, il.ComparisonOp.Equ, il.Constant(0, cond_var.type)))

        # handle stmt
        self.on_stmt(node.stmt)
        self.cur_func.add_stmt(il.GotoStmt(start_lbl))

        self.cur_func.place_label(end_lbl)

        self.loop_stack.pop()

    # nodes that do not evaluate
    def on_stmt(self, node):
        typ = type(node)
        if typ == c_ast.Typedef:
            self.on_typedef(node)
        elif typ == c_ast.Decl:
            self.on_decl(node)
        elif typ == c_ast.FuncDef:
            self.on_funcdef(node)
        elif typ == c_ast.If:
            self.on_if(node)
        elif typ == c_ast.Return:
            self.on_return(node)
        elif typ == c_ast.Compound:
            self.on_compound(node)
        elif typ == c_ast.EmptyStatement:
            pass
        elif typ == c_ast.While:
            self.on_while(node)
        elif typ == c_ast.Continue:
            self.on_continue_stmt(node)
        elif typ == c_ast.Break:
            self.on_break_stmt(node)
        # elif typ == c_ast.For:
        #     self.on_for(node)
        else:
            self.on_expr(node)

    def on_continue_stmt(self, node):
        assert type(node) == c_ast.Continue

        if not self.cur_func:
            raise SyntaxError("use of 'continue' outside of function")
        if not self.loop_stack:
            raise SyntaxError("use of 'continue' outside of loop")
        start_lbl, end_lbl = self.loop_stack[-1]
        self.cur_func.add_stmt(il.GotoStmt(start_lbl))


    def on_break_stmt(self, node):
        assert type(node) == c_ast.Break

        if not self.cur_func:
            raise SyntaxError("use of 'break' outside of function")
        if not self.loop_stack:
            raise SyntaxError("use of 'break' outside of loop")
        start_lbl, end_lbl = self.loop_stack[-1]
        self.cur_func.add_stmt(il.GotoStmt(end_lbl))

    def on_constant(self, const_type, value):
        il_var = self.cur_func.new_temporary(const_type, 0, None)
        assign_stmt = self.make_assign_stmt(il_var, il.Constant(value, const_type))
        self.cur_func.add_stmt(assign_stmt)
        return il_var

    def on_constant_node(self, node):
        if node.type == 'int':
            return self.on_constant(il.Types.int, node.value)
        else:
            raise RuntimeError('unsupported constant type ' + node.type)

    def on_postincrement(self, expr_node):
        expr_var = self.on_expr(expr_node) # lol, this will result in a blatant common subexpression
        self.on_preincrement(expr_node)
        return expr_var

    def on_preincrement(self, expr_node):
        # this is kinda hacky but w/e
        return self.on_assign(c_ast.Assignment('+=', expr_node, c_ast.Constant('int', 1)))

    def on_postdecrement(self, expr_node):
        expr_var = self.on_expr(expr_node)
        self.on_predecrement(expr_node)
        return expr_var

    def on_predecrement(self, expr_node):
        return self.on_assign(c_ast.Assignment('-=', expr_node, c_ast.Constant('int', 1)))

    def on_unary_op(self, node):
        if node.op == 'p++':
            return self.on_postincrement(node.expr)
        elif node.op == '++':
            return self.on_preincrement(node.expr)
        elif node.op == 'p--':
            return self.on_postdecrement(node.expr)
        elif node.op == '--':
            return self.on_predecrement(node.expr)

        expr_var = self.on_expr(node.expr)
        if node.op == '*':
            return self.make_dereference(expr_var)
        elif node.op == '&':
            return self.make_reference(expr_var)
        else:
            il_op = Compiler.parse_unary_op(node.op)
            dst_var = self.duplicate_var(expr_var)
            new_stmt = il.UnaryStmt(dst_var, il_op, expr_var)
            self.cur_func.add_stmt(new_stmt)
            return dst_var

    @staticmethod
    def parse_unary_op(op):
        if op == '!':
            return il.UnaryOp.Not
        else:
            raise RuntimeError('unsupported unary operation ' + op)

    def on_id_node(self, node):
        """Resolve an identifier (ID) node into a variable"""
        scope, ast_decl = self.current_scope.resolve_symbol(node.name)
        if not scope:
            raise SyntaxError('use of undeclared symbol ' + node.name)
        if scope.height == 0:
            # global
            assert False
        else:
            il_var = self.cur_func_c_locals[ast_decl]
            return il_var

    # nodes that evaluate. return an ILVariable holding the evaluated value
    def on_expr(self, node):
        typ = type(node)
        if typ == c_ast.Assignment:
            return self.on_assign(node)
        elif typ == c_ast.BinaryOp:
            return self.on_binary_op_node(node)
        elif typ == c_ast.ID:
            return self.on_id_node(node)
        elif typ == c_ast.Constant:
            return self.on_constant_node(node)
        elif typ == c_ast.UnaryOp:
            return self.on_unary_op(node)
        else:
            raise RuntimeError("unsupported ast expr node " + str(node))

    def compile_stmts(self, stmts):
        for node in stmts:
            self.on_stmt(node)

    def compile(self, ast):
        self.compile_stmts(ast.ext)

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
        if not decl_sign:
            decl_sign = 'signed'
        else:
            if decl_type != 'int' and decl_type != 'char':
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
            signedness, decl_size, decl_type = Compiler.interpret_identifier_type(node.names)
            builtin_type = Compiler.parse_decl_type(signedness, decl_size, decl_type)
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
