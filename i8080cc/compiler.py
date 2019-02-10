from pycparser import c_ast

class Scope(object):
    def __init__(self, parent=None):
        self.symbols = {}
        self.types = {}
        self.parent = parent

    def resolve_symbol(self, name):
        scope = self
        while scope:
            if name in scope.symbols:
                return scope.symbols[name]
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
        type_decl = self.resolve_type(name).type
        while type_decl:
            if type(type_decl) == c_ast.IdentifierType:
                assert len(type_decl.names) == 1
                name = type_decl.names[0]
                type_decl = self.resolve_type(name)
            elif type(type_decl) == c_ast.Struct:
                return type_decl
            else:
                raise RuntimeError("don't know how to resolve type " + str(type_decl))
        return name

class Compiler(object):
    def __init__(self):
        self.scope_stack = [ Scope() ] # global scope

    @property
    def current_scope(self):
        return self.scope_stack[-1]

    def scope_push(self):
        new_scope = Scope(self.current_scope)
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
        self.current_scope.types[typedef_name] = node.type

    def on_decl(self, node):
        assert type(node) == c_ast.Decl
        decl_name = node.name
        if decl_name in self.current_scope.symbols:
            raise SyntaxError("redefinition of %s" % (decl_name,))
        else:
            self.current_scope.symbols[decl_name] = node
            # handle initializer if there is one

    def on_funcdef(self, node):
        assert type(node) == c_ast.FuncDef
        func_decl = node.decl
        self.current_scope.symbols[func_decl.name] = func_decl

        # new scope
        new_scope = self.scope_push()

        # process parameters
        for param_decl in func_decl.type.args.params:
            self.on_decl(param_decl)

        # process body
        self.descend_into(node.body)
        print node

        # exit scope
        self.scope_pop(new_scope)

    def on_if(self, node):
        assert type(node) == c_ast.If
        # handle cond
        # handle iftrue
        # handle iffalse
        print node

    def on_return(self, node):
        assert type(node) == c_ast.Return
        # handle expr
        print node

    def on_node(self, node):
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
            raise RuntimeError("unsupported ast node " + str(node))

    def compile_stmts(self, stmts):
        for node in stmts:
            self.on_node(node)

    def compile(self, ast):
        self.compile_stmts(ast.ext)