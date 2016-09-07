"""
Container for models using generic relations provided by Django's ContentTypes framework.

References:
    https://docs.djangoproject.com/en/1.8/ref/contrib/contenttypes/#generic-relations
"""
try:
    # python3
    from collections import MutableMapping
except ImportError:
    # python2
    from collections.abc import MutableMapping

from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models

from pulp.platform.models import Model


class GenericRelationModel(Model):
    """Base model class for implementing Generic Relations.

    This class provides the required fields to implement generic relations. Instances of
    this class can only be related models with a UUID primary key, such as those subclassing
    Pulp's base Model class.
    """
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.UUIDField()
    content_object = GenericForeignKey('content_type', 'object_id')

    class Meta:
        abstract = True


class GenericKeyValueMutableMapping(MutableMapping):
    """MutableMapping implementation to provide dict-list access to a GenericKeyValueStore.

    For example, Repository has a notes field, so given Repository instance ``r``,
    ``r.notes.mapping['key'] = 'note value'`` will result in database write.
    ``r.notes.mapping['key']`` by itself will read from the database, and
    ``del(r.notes.mapping['key'])`` will delete the corresponding db entity.
    ``KeyError`` is raised when the corresponding DB row for a key does not exist.
    ``__iter__`` returns a generator of keys.

    Certain methods have been overridden to use the database more efficiently, where possible:
    ``__len__`` falls back to the manager's ``count`` method
    ``__contains__`` falls back to the manager's ``exists`` method
    ``items`` returns key/value pairs directly from model instances, rather than

    keys and values are stored in ``TextField``s, and will automatically be coerced to strings
    when saved to the database.

    """
    def __init__(self, manager):
        self.manager = manager

    def __getitem__(self, key):
        try:
            return self.manager.get(key=key).value
        except self.manager.model.DoesNotExist:
            raise KeyError(key)

    def __setitem__(self, key, value):
        self.manager.update_or_create(key=key, defaults={'value': value})

    def __delitem__(self, key):
        try:
            self.manager.get(key=key).delete()
        except self.manager.model.DoesNotExist:
            raise KeyError(key)

    def __iter__(self):
        return (kv.key for kv in self.manager.all())

    def __len__(self):
        return self.manager.count()

    def __contains__(self, key):
        return self.manager.filter(key=key).exists()

    def items(self):
        # we can save MutableMapping a step by returning key value pairs from Django as an
        # iterable, rather than making it __getitem__ for each key
        return ((kv.key, kv.value) for kv in self.manager.all())

    def clear(self):
        self.manager.all().delete()

    def values(self):
        return (kv.value for kv in self.manager.all())

    def __repr__(self):
        return '{}({})'.format(self.manager.model._meta.object_name, repr(dict(self)))


class GenericKeyValueManager(models.Manager):
    """A normal Django Manager with a mapping attribute providing the MutableMapping interface.

    This ties the GenericKeyValueMutableMapping together with the GenericKeyValueStore model.
    The mapping interface is available on a model instance as ``instance.kvfield.mapping``, where
    "kvfield" is the name of the GenericRelation field pointing to a GenericKeyValueStore
    subclass.
    """
    @property
    def mapping(self):
        return GenericKeyValueMutableMapping(self)


class GenericKeyValueStore(GenericRelationModel):
    """Generic model providing a Key/Value store that can be related to any other model."""
    # Because we have multiple types of Key/Value stores, this is an abstract base class that
    # can be easily subclasses to create the specific types. We could potentially support multiple
    # types of K/V stores with this single model (and thus store them in a single table), but
    # it's *way simpler* to make multiple tables and let Django keep track of everything.

    key = models.TextField()
    value = models.TextField()

    # Use the GenericKeyValueManager by default to let anything using a GenericKeyValueStore
    # have access to the mapping attr
    objects = GenericKeyValueManager()

    class Meta:
        abstract = True
        unique_together = ('key', 'content_type', 'object_id')


class Config(GenericKeyValueStore):
    """Used by pulp and users to store k/v config data on a model"""
    pass


class Notes(GenericKeyValueStore):
    """Used by users to store arbitrary k/v data on a model"""
    pass


class Scratchpad(GenericKeyValueStore):
    """Used by pulp to store arbitrary k/v data on a model."""
    pass
