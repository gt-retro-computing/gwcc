class EnumValue(object):
	def __init__(self, parent, name, value):
		self.parent = parent
		self.name = name
		self.value = value

	def __eq__(self, other):
		if other == None:
			return False

		is_other_val = isinstance(other, (EnumValue, FlagEnumComposite))

		if not is_other_val:
			import traceback
			traceback.print_stack()
			print 'Deprecation warning: EnumValue comparison with other types is deprecated'

		if is_other_val:
			return self is other or self.value == other.value
		else:
			return self.value == other

	def __str__(self):
		return '%s.%s' % (self.parent.__name__, self.name)

	def __repr__(self):
		return '<%s.%s val=%r>' % (self.parent.__name__, self.name, self.value)

class EnumFlagValue(EnumValue):
	def isset(self, other):
		if other.parent != self.parent:
			raise KeyError('Unmatched enum flag parents: %r %r' % (self.parent, other.parent,))

		return other == self

	def set(self, x):
		raise NotImplementedError('EnumFlagValue is immutable. Maybe you meant EnumFlagValue.asComposite().set(x)?')

	def unset(self, x):
		raise NotImplementedError('EnumFlagValue is immutable. Maybe you meant EnumFlagValue.asComposite().set(x)?')

	def asComposite(self):
		return FlagEnumComposite(self.parent, self)

	def isEmpty(self):
		return False

	def __or__(self, other):
		if isinstance(other, FlagEnumComposite):
			other.set(self)
			return other
		elif isinstance(other, EnumFlagValue):
			return FlagEnumComposite(self.parent, self, other)
		else:
			raise TypeError('%s cannot be or\'d with %r' % (self.__class__.__name__ ,other,))

	def __and__(self, other):
		if isinstance(other, (FlagEnumComposite, EnumValue)):
			if other.parent != self.parent:
				raise KeyError('Unmatched enum flag parents: %r %r' % (self.parent, other.parent,))

			return self.parent.get(self.value & other.value)
		else:
			raise TypeError('%s cannot be and\'d with %r' % (self.__class__.__name__ ,other,))

class FlagEnumComposite(EnumFlagValue):
	def __init__(self, parent, *args):
		self.parent = parent
		self.values = set()
		self.value = 0

		for x in args:
			self.set(x)

	def asComposite(self):
		return self

	def copy(self):
		return FlagEnumComposite(self.parent, *self.values)

	def set(self, x):
		"""
		Args:
		    x (EnumFlagValue | core.util.enum.EnumFlagValue | FlagEnumComposite | core.util.enum.FlagEnumComposite): stuff
		"""
		if x.parent != self.parent:
			raise KeyError('Unmatched enum flag parents: %r %r' % (self.parent, x.parent,))

		# to support setting multiple values (FlagEnumComposite)
		_iter = [x] if isinstance(x, EnumFlagValue) else x.values

		for x in _iter:
			if x in self.values:
				return

			self.values.add(x)
			self.value |= x.value

	def unset(self, x):
		"""
		Args:
		    x (EnumFlagValue | core.util.enum.EnumFlagValue | FlagEnumComposite | core.util.enum.FlagEnumComposite): stuff
		"""
		if x.parent != self.parent:
			raise KeyError('Unmatched enum flag parents: %r %r' % (self.parent, x.parent,))

		# to support unsetting multiple values (FlagEnumComposite)
		_iter = [x] if isinstance(x, EnumFlagValue) else x.values

		for x in _iter:
			if not x in self.values:
				return

			self.values.remove(x)
			self.value ^= x.value

	def isset(self, x):
		"""
		Args:
		    x (EnumFlagValue | core.util.enum.EnumFlagValue | FlagEnumComposite | core.util.enum.FlagEnumComposite): stuff
		"""
		if x.parent != self.parent:
			raise KeyError('Unmatched enum flag parents: %r %r' % (self.parent, x.parent,))

		# avoid checking the list for x
		return self.value & x.value == x.value

	def isEmpty(self):
		return self.value == 0

	def _recalculate(self):
		self.value = 0

		for x in self.values:
			self.value |= x.value

	def __or__(self, other):
		if isinstance(other, FlagEnumComposite):
			if other.parent != self.parent:
				raise KeyError('Unmatched enum flag parents: %r %r' % (self.parent, other.parent,))

			self.values.update(other.values)
			self._recalculate()
		elif isinstance(other, EnumValue):
			self.set(other)
		else:
			raise TypeError('%s cannot be or\'d with %r' % (self.__class__.__name__ ,other,))

		return self

	def __and__(self, other):
		if isinstance(other, (FlagEnumComposite, EnumValue)):
			if other.parent != self.parent:
				raise KeyError('Unmatched enum flag parents: %r %r' % (self.parent, other.parent,))

			return self.parent.get(self.value & other.value)
		else:
			raise TypeError('%s cannot be and\'d with %r' % (self.__class__.__name__ ,other,))

	def __str__(self):
		return '%s %s' % (self.parent.__name__, ' | '.join([x.name for x in sorted(self.values, key=lambda j: j.value)]))

	def __repr__(self):
		return '<%s val=%s>' % (self.parent.__name__, ' | '.join([x.name for x in sorted(self.values, key=lambda j: j.value)]))

class EnumMetaclass(type):
	def __init__(cls, name, bases, d):
		values = {}
		try:
			isflag = issubclass(cls, FlagEnum)
		except NameError:
			isflag = False

		for k,v in d.iteritems():
			# classmethods won't have __call__ until the class is defined
			if k.startswith('__') or hasattr(v, '__call__') or hasattr(v, '__func__'):
				continue

			ev = EnumValue(cls, k, v) if not isflag else EnumFlagValue(cls, k, v)
			d[k] = ev
			setattr(cls, k, ev)
			values[v] = ev

		cls._values = values

		if isflag:
			cls._sorted_values = sorted([(k,v) for k,v in cls._values.iteritems()], key=lambda x: x[0])[::-1]

		super(EnumMetaclass, cls).__init__(name, bases, d)

_NO_DEFAULT = object()

class Enum(object):
	__metaclass__ = EnumMetaclass

	@classmethod
	def get(cls, value, default=_NO_DEFAULT):
		if default == _NO_DEFAULT:
			return cls._values[value]
		else:
			return cls._values.get(value, default)


class FlagEnum(Enum):
	__metaclass__ = EnumMetaclass

	@classmethod
	def all(cls):
		return FlagEnumComposite(cls, *[flag for flagvalue, flag in cls._sorted_values])

	@classmethod
	def empty(cls):
		return FlagEnumComposite(cls)

	@classmethod
	def get(cls, value):
		ret = cls._values.get(value, None)

		if ret:
			return ret

		ret = []

		for flagvalue, flag in cls._sorted_values:
			# we can't possibly match a value we're lower than
			if flagvalue > value:
				continue

			if value & flagvalue == flagvalue:
				ret.append(flag)
				value = value ^ flagvalue

		if value > 0:
			raise KeyError('Unable to find flags for value (%s): %s' % (value, bin(value)))

		return FlagEnumComposite(cls, *ret)

def main():
	class TestEnum(FlagEnum):
		A = 0x01
		B = 0x02
		C = 0x04
		D = 0x08

	print TestEnum.get(8 + 2 + 1)
	print TestEnum.A | TestEnum.D
	print (TestEnum.A | TestEnum.D).value

if __name__ == '__main__':
	main()