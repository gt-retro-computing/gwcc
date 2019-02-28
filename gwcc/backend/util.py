

class BackendError(SyntaxError):
    def __init__(self, message):
        super(BackendError, self).__init__(message)
