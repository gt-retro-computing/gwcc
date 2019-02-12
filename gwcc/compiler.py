"""
The gangweed C compiler
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

        print self.cur_func.stmts

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
        new_stmt = il.ILUnaryStmt(self.cur_func_retvar, il.ILUnaryOp.Identity, retval)
        self.cur_func.add_stmt(new_stmt)

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
        # TODO: do cast
        # TODO: promotion rules
        new_var = self.new_temporary(srcA.type)
        new_stmt = il.ILBinaryStmt(new_var, il_op, srcA, srcB)
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

    def c_ast_type_to_il_type(self, node):
        if type(node) == c_ast.IdentifierType:
            if 'signed' in node.names and 'unsigned' in node.names:
                raise SyntaxError('type is declared as both unsigned and signed')
            unsigned = 'unsigned' in node.names
            il_type = None
            for name in node.names:
                if name == 'signed':
                    pass # discard
                elif name == 'unsigned':
                    pass # discard
                elif name == 'char':
                    if il_type:
                        raise SyntaxError('double type declaration')
                    il_type = il.ILTypes.uchar if unsigned else il.ILTypes.char
                elif name == 'short':
                    if il_type:
                        raise SyntaxError('double type declaration')
                    il_type = il.ILTypes.ushort if unsigned else il.ILTypes.short
                elif name == 'int':
                    if il_type:
                        raise SyntaxError('double type declaration')
                    il_type = il.ILTypes.uint if unsigned else il.ILTypes.int
                elif name == 'long':
                    if il_type:
                        if il_type == il.ILTypes.int:
                            pass
                        elif il_type == il.ILTypes.long:
                            raise SyntaxError('long long is not supported')
                        else:
                            raise SyntaxError('invalid syntax in type decl %s' + ' '.join(node.names))
                    il_type = il.ILTypes.ulong if unsigned else il.ILTypes.long
                elif name == 'void':
                    if il_type:
                        raise SyntaxError('double type declaration')
                    if 'signed' in node.names or 'unsigned' in node.names:
                        raise SyntaxError('signed/unsigned void type')
                    il_type = il.ILTypes.void
                elif name == 'float':
                    if il_type:
                        raise SyntaxError('double type declaration')
                    raise SyntaxError('floating point is fake news')
                elif name == 'double':
                    if il_type:
                        raise SyntaxError('double type declaration')
                    raise SyntaxError('this is an 8080. wtf are you thinking?')
                else:
                    # try to resolve
                    il_type = self.c_ast_type_to_il_type(self.current_scope.resolve_basetype(name))
            assert il_type
            return il_type
        elif type(node) == c_ast.PtrDecl:
            return il.ILTypes.ptr
        else:
            raise RuntimeError("unsupported ast type decl " + str(node))

