import sys
import re
import types

if sys.version >= '3':
    from itertools import zip_longest
    string = str
else:
    from itertools import izip_longest as zip_longest
    string = basestring

from .field import basefield

class NodeBase(type):
    """ Metaclass for AST Nodes
    Verifies the syntax of the declarative field syntax
    """
    def __new__(cls, name, bases, attrs):
        parents = [b for b in bases if isinstance(b, NodeBase)]
        if not parents:
            return type.__new__(cls, name, bases, attrs)
        guards = {}
        for base in bases:
            if isinstance(base, NodeBase) and hasattr(base, '_guards'):
                guards.update(base._guards)
        for k, v in attrs.items():
            if k == '_template':
                if not isinstance(v, (string, property)) and not hasattr(v, '__call__'):
                    raise TypeError("_template must be a string")
                continue
            if k.startswith('_') or hasattr(v, '__call__'):
                continue
            if not isinstance(v, dict) or not issubclass(v['field_cls'], basefield):
                raise TypeError('Field type must be a subclass of basefield')
            if not all(isinstance(i, (type,
                                      str,
                                      re._pattern_type)) for i in v['types']):
                raise TypeError('Field types must be python types or strings')
            guards[k] = v
        fields = [i[0] for i in sorted(guards.items(),
                                       key=lambda x: x[1]['_counter'])]
        attrs['_guards'] = guards
        attrs['_fields'] = fields
        if not '_abstract' in attrs.keys():
            attrs['_abstract'] = False
        return type.__new__(cls, name, bases, attrs)

# Temporary solution for metaclass in py2 vs py3
if sys.version >= '3':
    TempNode = NodeBase("NodeBase", (object,), {})
else:
    TempNode = object


def stringify(node):
    if isinstance(node, string):
        return string(node)
    return node.__repr__()

def gettemplate(node, name=None):
    template = None
    name = "_template_%s" % name if name else "_template"
    if hasattr(node, name):
        template = getattr(node, name)
    if hasattr(template, '__call__'):
        template = template()
    elif hasattr(node, '_%s' % name):
        template = getattr(node, '_%s' % name)
    return template

class Node(TempNode):
    """Basic AST Node

    Any Node should subclass from this one
    """
    __metaclass__ = NodeBase

    ####
    #
    # The debug mode allows user to enforce type checks in AST based classes
    #
    # The cost is ~2x slower performance on operations around AST classes.
    #
    ####
    _debug = True

    def __init__(self, *args, **kwargs):
        key = 0
        if self._debug and self._abstract:
            raise TypeError('Class %s is abstract' % self.__class__.__name__)
        for name in self._fields:
            if name in kwargs:
                val = kwargs.pop(name)
            else:
                try:
                    val = args[key]
                    key += 1
                except IndexError:
                    val = self._guards[name]['default']
                    if hasattr(val, '__iter__'):
                        val = val[:]
            if self._debug:
                guards = self._guards
                val = guards[name]['field_cls'].init(name,
                                                     val,
                                                     guards[name])
                setattr(self.__class__, '__delattr__', self.__debug__delattr__)
                setattr(self.__class__, '__setattr__', self.__debug__setattr__)
                self.__debug__setattr__(name, val)
            else:
                object.__setattr__(self, name, val)

    def __getitem__(self, key):
        if hasattr(self, key):
            return getattr(self, key)
        raise KeyError(key)

    def __repr__(self, serializer=None):
        print('beg repr on %s' % type(self))
        template = gettemplate(self)
        if template:
            fields = {}
            for i in self._fields:
                field = getattr(self, i)
                if isinstance(field, list):
                    if hasattr(self, '_template_%s' % i):
                        list_template = getattr(self, '_template_%s' % i)
                        fields[i] = ''.join(['%s%s' % x for x in zip_longest(
                                                        map(stringify, field),
                                                        list_template,
                                                        fillvalue=''
                                                        )])
                    else:
                        fields[i] = ', '.join(map(stringify, field))
                else:
                    if field is None:
                        fields[i] = ''
                    else:
                        fields[i] = stringify(field)
            print('end repr on %s' % type(self))
            return template % fields
        #if serializer:
        #    return serializer.dump(self)
        #if len(self._fields) == 1:
        #    return getattr(self, self._fields[0]).__repr__()
        print('end repr on %s' % type(self))
        return object.__repr__(self)

    def __debug__setattr__(self, name, val):
        if name in self._fields:
            val = self._guards[name]['field_cls'].init(name,
                                                      val,
                                                      self._guards[name])
        # there's a bug here when setattr is called on an object with an 
        # attribute
        # that has been previously defined.
        # See l20n's js compiler and macro idrefs substitution
        object.__setattr__(self, name, val)

    def __debug__delattr__(self, name):
        if name in self._fields:
            raise Exception("Cannot remove Node's fields")
        object.__delattr__(self, name)
