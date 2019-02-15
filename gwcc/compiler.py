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
        return None

    def resolve_type(self, name):
        scope = self
        while scope:
            if name in scope.types:
                return scope.types[name]
            scope = scope.parent
        return None

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
    def __init__(self):
        self.scope_stack = [ Scope() ]

        self.cur_func = None
        self.cur_func_c_locals = None # map from ast data to IRVariable
        self.cur_func_retvar = None
        self.cur_func_temporaries = {}

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

    def descend_into(self, compound):
        """
        Descend into a block, pushing a new scope onto the scope stack, and compile all statements in the block.
        Afterwards, pop and discard the newly-made scope off from the scope stack.
        :param compound: instance of c_ast.Compound
        """
        assert type(compound) == c_ast.Compound
        new_scope = self.scope_push()
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

            if self.cur_func: # we are in a function -> this is a local decl.
                # handle initializer if there is one
                il_var = il.ILVariable('_local_' + str(self.current_scope_depth) + '_' + node.name, self.c_ast_type_to_il_type(node.type.type))
                self.cur_func_c_locals[node] = il_var
                print 'new decl ' + str(node)
                return il_var

    def new_temporary(self, typ):
        assert self.cur_func
        name = 't' + str(len(self.cur_func_temporaries))
        il_var = il.ILVariable(name, typ)
        self.cur_func_temporaries[il_var] = il_var
        return il_var

    def assign(self, dst, src):
        assert type(dst) == il.ILVariable
        assert type(src) == il.ILVariable
        if dst.type != src.type:
            return il.ILCastStmt(dst, src)
        return il.ILUnaryStmt(self.cur_func_retvar, il.ILUnaryOp.Identity, src)

    def on_funcdef(self, node):
        assert type(node) == c_ast.FuncDef
        func_decl = node.decl
        self.current_scope.symbols[func_decl.name] = func_decl

        # new scope
        new_scope = self.scope_push()
        self.cur_func_c_locals = {}
        self.cur_func_temporaries = {}

        # return val
        self.cur_func_retvar = il.ILVariable('_retval', self.c_ast_type_to_il_type(func_decl.type.type.type))
        # process parameters
        argvars = []
        for param_decl in func_decl.type.args.params:
            argvars.append(self.on_decl(param_decl))

        self.cur_func = il.ILFunction(func_decl.name, argvars, self.cur_func_retvar)

        # process body
        self.descend_into(node.body)
        # print node

        print '\n'.join(map(str,self.cur_func.stmts))

        # exit scope
        self.scope_pop(new_scope)
        self.cur_func = None
        self.cur_func_c_locals = None
        self.cur_func_retvar = None
        self.cur_func_temporaries = None

    def on_if(self, node):
        assert type(node) == c_ast.If
        # handle cond
        # handle iftrue
        # handle iffalse
        # print node

    def on_return(self, node):
        assert type(node) == c_ast.Return
        assert self.cur_func_retvar
        retval = self.on_expr(node.expr)

        self.cur_func.add_stmt(self.assign(self.cur_func_retvar, retval))

    def on_binary_op(self, node):
        print node
        srcA = self.on_expr(node.left)
        srcB = self.on_expr(node.right)
        op = node.op
        if op == '+':
            il_op = il.ILBinaryOp.Add
        elif op == '-':
            il_op = il.ILBinaryOp.Sub
        elif op == '*':
            il_op = il.ILBinaryOp.Mul
        else:
            raise ValueError('unsupported binary operation ' + op)

        a_type, b_type = srcA.type, srcB.type
        if srcA.type == srcB.type:
            srcA_casted = srcA
            srcB_casted = srcB
        elif il.ILTypes.is_less_than(a_type, b_type):
            srcA_casted = self.new_temporary(b_type)
            cast_stmt = self.assign(srcA_casted, srcA)
            self.cur_func.add_stmt(cast_stmt)
            srcB_casted = srcB
        elif il.ILTypes.is_less_than(b_type, a_type):
            srcA_casted = srcA
            srcB_casted = self.new_temporary(a_type)
            cast_stmt = self.assign(srcB_casted, srcB)
            self.cur_func.add_stmt(cast_stmt)
        else:
            assert False # wtf

        new_var = self.new_temporary(srcA_casted.type)
        new_stmt = il.ILBinaryStmt(new_var, il_op, srcA_casted, srcB_casted)
        self.cur_func.add_stmt(new_stmt)
        return new_var

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
        else:
            raise RuntimeError("unsupported ast stmt node " + str(node))

    # nodes that evaluate. return an ILVariable holding the evaluated value
    def on_expr(self, node):
        typ = type(node)
        if typ == c_ast.BinaryOp:
            return self.on_binary_op(node)
        elif typ == c_ast.ID:
            scope, ast_decl = self.current_scope.resolve_symbol(node.name)
            if scope.height == 0:
                # global
                assert False
            else:
                il_var = self.cur_func_c_locals[ast_decl]
                print il_var
                return il_var
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

    def c_ast_type_to_il_type(self, node):
        if type(node) == c_ast.IdentifierType:
            signedness, decl_size, decl_type = Compiler.interpret_identifier_type(node.names)
            unsigned = signedness == 'unsigned'
            if decl_type == 'char':
                return il.ILTypes.uchar if unsigned else il.ILTypes.char
            elif decl_type == 'int':
                if decl_size == 'short':
                    return il.ILTypes.ushort if unsigned else il.ILTypes.short
                elif decl_size == 'long':
                    return il.ILTypes.ulong if unsigned else il.ILTypes.long
                elif decl_size == 'longlong':
                    return il.ILTypes.ulonglong if unsigned else il.ILTypes.longlong
                else:
                    return il.ILTypes.uint if unsigned else il.ILTypes.int
            elif decl_type == 'void':
                return il.ILTypes.void
            elif decl_type == 'float':
                return il.ILTypes.float
            elif decl_type == 'double':
                if decl_size == 'long':
                    return il.ILTypes.longdouble
                else:
                    return il.ILTypes.double
            else:
                # try to resolve
                return self.c_ast_type_to_il_type(self.current_scope.resolve_basetype(decl_type))
        elif type(node) == c_ast.PtrDecl:
            return il.ILTypes.ptr
        else:
            raise RuntimeError("unsupported ast type decl " + str(node))

