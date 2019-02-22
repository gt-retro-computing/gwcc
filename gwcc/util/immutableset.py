class ImmutableSet(object):
    """
    Wraps an existing set to make it immutable.
    """
    def __init__(self, data):
        self._data = data

    def __getitem__(self, i):
        return self._data[i]

    def __iter__(self):
        return self._data.__iter__()

    def __nonzero__(self):
        return len(self._data) != 0

    def __str__(self):
        return self._data.__str__()

    def __len__(self):
        return self._data.__len__()

    def __eq__(self, other):
        return self._data.__eq__(other)

    def __hash__(self):
        return self._data.__hash__()
