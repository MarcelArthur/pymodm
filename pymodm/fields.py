# Copyright 2016 MongoDB, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""PyMongo ODM Field Definitions."""

import collections
import datetime
import decimal
import ipaddress
import re
import uuid
from collections import OrderedDict

from gridfs import GridFSBucket

import bson
from bson.binary import Binary
from bson.code import Code

_HAS_DECIMAL128 = True
try:
    from bson.decimal128 import Decimal128
except ImportError:
    _HAS_DECIMAL128 = False

from bson.errors import InvalidId
from bson.objectid import ObjectId
from bson.int64 import Int64
from bson.regex import Regex
from bson.timestamp import Timestamp

_HAS_PILLOW = True
try:
    from PIL import Image
except ImportError:
    _HAS_PILLOW = False


from pymodm import validators
from pymodm.base.fields import RelatedModelFieldsBase
from pymodm.common import _import
from pymodm.compat import text_type, string_types, PY3
from pymodm.connection import _get_db
from pymodm.errors import ValidationError, ConfigurationError
from pymodm.base.fields import MongoBaseField
from pymodm.files import File, GridFSStorage, FieldFile, ImageFieldFile
from pymodm.vendor import parse_datetime


class CharField(MongoBaseField):
    """A unicode string field."""

    def __init__(self, verbose_name=None, mongo_name=None,
                 min_length=None, max_length=None, **kwargs):
        super(CharField, self).__init__(verbose_name=verbose_name,
                                        mongo_name=mongo_name,
                                        **kwargs)
        self.max_length = max_length

        self.validators.append(
            validators.validator_for_length(min_length, max_length))

    def to_python(self, value):
        return text_type(value)


class IntegerField(MongoBaseField):
    """A field that stores a Python int."""

    def __init__(self, verbose_name=None, mongo_name=None,
                 min_value=None, max_value=None, **kwargs):
        super(IntegerField, self).__init__(verbose_name=verbose_name,
                                           mongo_name=mongo_name,
                                           **kwargs)
        self.validators.append(
            validators.together(
                validators.validator_for_func(int),
                validators.validator_for_min_max(min_value, max_value)))

    def to_python(self, value):
        try:
            return int(value)
        except ValueError:
            return value


class BigIntegerField(IntegerField):
    """A field that always stores and retrieves numbers as bson.int64.Int64."""
    def to_python(self, value):
        try:
            return Int64(value)
        except ValueError:
            return value


class ObjectIdField(MongoBaseField):
    """A field that stores ObjectIds."""
    def __init__(self, verbose_name=None, mongo_name=None, **kwargs):
        super(ObjectIdField, self).__init__(verbose_name=verbose_name,
                                            mongo_name=mongo_name,
                                            **kwargs)

        self.validators.append(
            validators.validator_for_func(ObjectId))

    def to_mongo(self, value):
        if isinstance(value, ObjectId):
            return value
        try:
            return ObjectId(value)
        except (InvalidId, TypeError):
            raise ValidationError('%r is not a valid ObjectId hex string.'
                                  % value)

    def to_python(self, value):
        if isinstance(value, ObjectId):
            return value
        try:
            return ObjectId(value)
        except (InvalidId, TypeError):
            return value


class BinaryField(MongoBaseField):
    """A field that stores binary data."""
    def __init__(self, subtype=bson.binary.BINARY_SUBTYPE,
                 verbose_name=None, mongo_name=None, **kwargs):
        super(BinaryField, self).__init__(verbose_name=verbose_name,
                                          mongo_name=mongo_name,
                                          **kwargs)
        """
        Create a new BinaryField.

        :parameters:
          - `subtype` - One of the subtypes listed in the `bson.binary` module.

        """
        self.subtype = subtype
        self.validators.append(validators.validator_for_func(Binary))

    def to_mongo(self, value):
        if isinstance(value, Binary):
            return value
        try:
            return Binary(value, subtype=self.subtype)
        except (TypeError, ValueError) as exc:
            raise ValidationError(exc)

    def to_python(self, value):
        if isinstance(value, Binary):
            return value
        try:
            return Binary(value, subtype=self.subtype)
        except (TypeError, ValueError):
            return value


class BooleanField(MongoBaseField):
    """A field that stores boolean values."""
    def to_python(self, value):
        return bool(value)


class DateTimeField(MongoBaseField):
    """A field that stores :class:`~datetime.datetime` objects."""
    def __init__(self, verbose_name=None, mongo_name=None, **kwargs):
        super(DateTimeField, self).__init__(verbose_name=verbose_name,
                                            mongo_name=mongo_name,
                                            **kwargs)
        self.validators.append(self.to_mongo)

    def to_mongo(self, value):
        if isinstance(value, datetime.datetime):
            return value
        elif isinstance(value, datetime.date):
            return datetime.datetime(value.year, value.month, value.day)
        elif isinstance(value, string_types):
            return parse_datetime(value)
        raise ValidationError(
            '%r cannot be converted to a datetime object.' % value)

    def to_python(self, value):
        try:
            return self.to_mongo(value)
        except ValidationError:
            return value


class Decimal128Field(MongoBaseField):
    """A field that stores :class:`~bson.decimal128.Decimal128` objects.

    .. note:: This requires MongoDB >= 3.4.

    """

    def __init__(self, min_value=None, max_value=None,
                 verbose_name=None, mongo_name=None, **kwargs):
        """
        Create a new DecimalField.

        :parameters:
          - `min_value` - The minimum value that can be stored in this field.
          - `max_value` - The maximum value that can be stored in this field.
        """
        if not _HAS_DECIMAL128:
            raise ConfigurationError(
                'Need PyMongo >= 3.4 in order to use Decimal128Field.')

        super(Decimal128Field, self).__init__(verbose_name=verbose_name,
                                              mongo_name=mongo_name,
                                              **kwargs)

        def validate_min_and_max(value):
            # Turn value into a Decimal.
            value = value.to_decimal()
            validators.validator_for_min_max(min_value, max_value)(value)

        self.validators.append(
            validators.together(
                validators.validator_for_func(self.to_mongo),
                validate_min_and_max))

    def to_mongo(self, value):
        if isinstance(value, Decimal128):
            return value
        try:
            return Decimal128(decimal.Decimal(value))
        except decimal.DecimalException as exc:
            raise ValidationError(
                'Cannot convert value %r to Decimal128: %s'
                % (value, exc.__class__.__name__))

    def to_python(self, value):
        try:
            return self.to_mongo(value)
        except ValidationError:
            return value


class EmailField(MongoBaseField):
    """A field that stores email addresses."""
    # Better to accept than reject email addresses.
    # Just assert that there is one '@' sign.
    EMAIL_PATTERN = re.compile(r'^[^@]+@[^@]+$')

    def __init__(self, verbose_name=None, mongo_name=None, **kwargs):
        super(EmailField, self).__init__(verbose_name=verbose_name,
                                         mongo_name=mongo_name,
                                         **kwargs)

        def validate_email(value):
            if not re.match(self.EMAIL_PATTERN, value):
                raise ValidationError(
                    '%s is not a valid email address.' % value)
        self.validators.append(validate_email)


class FileField(MongoBaseField):
    """A field that stores files.

    :parameters:
      - `storage` - The :class:`~pymodm.files.Storage` implementation to
        use for saving and opening files.

    """
    _wrapper_class = FieldFile

    def __init__(self, verbose_name=None, mongo_name=None,
                 storage=None, **kwargs):
        super(FileField, self).__init__(verbose_name=verbose_name,
                                        mongo_name=mongo_name,
                                        **kwargs)
        self.storage = storage

    def to_mongo(self, value):
        file_obj = self.to_python(value)
        # Save the file and return its name.
        if not file_obj._committed:
            file_obj.save(value.name, value)
        return file_obj.name

    def _to_field_file(self, value, inst):
        if isinstance(value, FieldFile):
            # No need to convert anything.
            return value

        # Convert builtin 'file' and others to a File object.
        if (not isinstance(value, File) and
                hasattr(value, 'read') and hasattr(value, 'name')):
            value = File(value, value.name, getattr(value, 'metadata', None))

        # Wrap File objects in a FieldFile.
        if isinstance(value, File):
            ff = self._wrapper_class(inst, self, value.name)
            ff.file = value
            ff._committed = False
            return ff

        # Value might be the name/id of some file.
        return self._wrapper_class(inst, self, value)

    def __get__(self, inst, owner):
        MongoModelBase = _import('pymodm.base.models.MongoModelBase')
        if inst is not None and isinstance(inst, MongoModelBase):
            raw_value = inst._data.get(self.attname, self.default)
            if self.is_blank(raw_value):
                return raw_value
            # Turn whatever value we have into a FieldFile instance.
            _file = self._to_field_file(inst._data[self.attname], inst)
            # Store this transformed value back into the instance.
            inst._data[self.attname] = _file
            return self.to_python(_file)
        # Access from outside a Model instance.
        return self

    def contribute_to_class(self, cls, name):
        super(FileField, self).contribute_to_class(cls, name)
        gridfs = GridFSBucket(_get_db(self.model._mongometa.connection_alias))
        # Default GridFS storage.
        self.storage = self.storage or GridFSStorage(gridfs)


class ImageField(FileField):
    """A field that stores images."""
    _wrapper_class = ImageFieldFile

    def __init__(self, verbose_name=None, mongo_name=None, storage=None,
                 **kwargs):
        if not _HAS_PILLOW:
            raise ConfigurationError(
                'The PIL or Pillow library must be installed in order '
                'to use ImageField.')
        super(ImageField, self).__init__(verbose_name=verbose_name,
                                         mongo_name=mongo_name,
                                         storage=storage,
                                         **kwargs)
        self.validators.append(validators.validator_for_func(Image.open))


class FloatField(MongoBaseField):
    """A field that stores Python `float`s."""
    def __init__(self, verbose_name=None, mongo_name=None,
                 min_value=None, max_value=None, **kwargs):
        super(FloatField, self).__init__(verbose_name=verbose_name,
                                         mongo_name=mongo_name,
                                         **kwargs)
        self.validators.append(
            validators.together(
                validators.validator_for_func(float),
                validators.validator_for_min_max(min_value, max_value)))

    def to_mongo(self, value):
        try:
            return float(value)
        except ValueError as e:
            raise ValidationError(e)

    def to_python(self, value):
        try:
            return float(value)
        except ValueError:
            return value


class GenericIPAddressField(MongoBaseField):
    """A field that stores IPV4 and/or IPV6 addresses."""
    IPV4 = 0
    IPV6 = 1
    BOTH = 2

    def __init__(self, verbose_name=None, mongo_name=None, protocol=BOTH,
                 **kwargs):
        """Field representing IP addresses.

        :parameters:
          - `protocol` What protocol this Field should accept.
        """
        super(GenericIPAddressField, self).__init__(verbose_name=verbose_name,
                                                    mongo_name=mongo_name,
                                                    **kwargs)
        self.protocol = protocol

        def validate_ip_address(value):
            if not PY3 and isinstance(value, str):
                value = unicode(value)
            try:
                if GenericIPAddressField.IPV4 == self.protocol:
                    ipaddress.IPv4Address(value)
                elif GenericIPAddressField.IPV6 == self.protocol:
                    ipaddress.IPv6Address(value)
                elif GenericIPAddressField.BOTH == self.protocol:
                    ipaddress.ip_address(value)
            except (ValueError, ipaddress.AddressValueError):
                raise ValidationError('%r is not a valid IP address.' % value)
        self.validators.append(validate_ip_address)


class URLField(MongoBaseField):
    """A field that stores URLs."""
    SCHEMES = set(['http', 'https', 'ftp', 'ftps'])
    DOMAIN_PATTERN = re.compile(
        '(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+'
        '(?:[A-Z]{2,6}\.?|[A-Z0-9-]{2,}(?<!-)\.?)'  # domain
        '(?::\d+)?\Z',  # optional port
        re.IGNORECASE
    )
    PATH_PATTERN = re.compile('\A\S*\Z')

    def __init__(self, verbose_name=None, mongo_name=None, **kwargs):
        super(URLField, self).__init__(verbose_name=verbose_name,
                                       mongo_name=mongo_name,
                                       **kwargs)

        def validate_url(url):
            scheme, rest = url.split('://')
            if scheme.lower() not in self.SCHEMES:
                raise ValidationError('Unrecognized scheme: ' + scheme)
            domain, _, path = rest.partition('/')
            if not re.match(self.PATH_PATTERN, path):
                raise ValidationError('Invalid path: ' + path)
            if not re.match(self.DOMAIN_PATTERN, domain):
                # Maybe it's an ip address?
                if not PY3 and isinstance(domain, str):
                    domain = unicode(domain)
                try:
                    ipaddress.ip_address(domain)
                except ValueError:
                    try:
                        # Maybe there's a port. Remove it, and try again.
                        domain, port = domain.rsplit(':', 1)
                        ipaddress.ip_address(domain)
                    except ValueError:
                        raise ValidationError('Invalid URL: ' + rest)
        self.validators.append(validate_url)


class UUIDField(MongoBaseField):
    """A field that stores :class:`~uuid.UUID`s."""
    def __init__(self, verbose_name=None, mongo_name=None, **kwargs):
        super(UUIDField, self).__init__(verbose_name=verbose_name,
                                        mongo_name=mongo_name,
                                        **kwargs)
        self.validators.append(self.to_mongo)

    def to_mongo(self, value):
        if isinstance(value, uuid.UUID):
            return value
        try:
            return uuid.UUID(value)
        except ValueError as e:
            raise ValidationError(e)

    def to_python(self, value):
        try:
            return self.to_mongo(value)
        except ValidationError:
            return value


class RegularExpressionField(MongoBaseField):
    """A field that stores MongoDB regular expression types."""
    def __init__(self, verbose_name=None, mongo_name=None, **kwargs):
        super(RegularExpressionField, self).__init__(verbose_name=verbose_name,
                                                     mongo_name=mongo_name,
                                                     **kwargs)

    def to_python(self, value):
        try:
            if isinstance(value, Regex):
                return value.try_compile()
        except re.error:
            pass
        # Still return the Regex even if it's not Python-compatible, so at least
        # the value can be accessed.
        return value

    def to_mongo(self, value):
        # Allow bson module to handle both Python pattern and bson's Regex.
        return value


class JavaScriptField(MongoBaseField):
    """A field that stores JavaScript code."""
    def __init__(self, verbose_name=None, mongo_name=None, **kwargs):
        super(JavaScriptField, self).__init__(verbose_name=verbose_name,
                                              mongo_name=mongo_name,
                                              **kwargs)
        self.validators.append(self.to_mongo)

    def to_mongo(self, value):
        if isinstance(value, Code):
            return value
        try:
            return Code(value)
        except TypeError as e:
            raise ValidationError(e)

    def to_python(self, value):
        try:
            return self.to_mongo(value)
        except ValidationError:
            return value


class TimestampField(MongoBaseField):
    """A field that stores a BSON timestamp."""
    def __init__(self, verbose_name=None, mongo_name=None, **kwargs):
        super(TimestampField, self).__init__(verbose_name=verbose_name,
                                             mongo_name=mongo_name,
                                             **kwargs)
        self.validators.append(self.to_mongo)

    def to_mongo(self, value):
        if isinstance(value, Timestamp):
            return value
        elif isinstance(value, datetime.datetime):
            return Timestamp(value, 0)
        elif isinstance(value, string_types):
            try:
                return Timestamp(parse_datetime(value), 0)
            except (ValueError, TypeError):
                pass
        raise ValidationError('%r cannot be converted to a Timestamp.' % value)

    def to_python(self, value):
        try:
            return self.to_mongo(value)
        except ValidationError:
            return value


class DictField(MongoBaseField):
    """A field that stores a regular Python dictionary."""
    def __init__(self, verbose_name=None, mongo_name=None, **kwargs):
        super(DictField, self).__init__(verbose_name=verbose_name,
                                        mongo_name=mongo_name,
                                        **kwargs)

        self.validators.append(self.to_mongo)

        def validate_keys(value):
            for key in value:
                if not isinstance(key, string_types):
                    raise ValidationError(
                        'All dictionary keys must be strings: %r' % value)
                if '.' in key or '$' in key:
                    raise ValidationError(
                        'Dictionary keys must not contain "$" or ".": %r'
                        % value)
        self.validators.append(validate_keys)

    def to_mongo(self, value):
        if isinstance(value, collections.Mapping):
            return value
        try:
            return dict(value)
        except ValueError as e:
            raise ValidationError(e)

    def to_python(self, value):
        try:
            return self.to_mongo(value)
        except ValidationError:
            return value


class OrderedDictField(DictField):
    """A field that stores a :class:`~collections.OrderedDict`."""
    def __init__(self, field=None, verbose_name=None, mongo_name=None,
                 **kwargs):
        super(OrderedDictField, self).__init__(verbose_name=verbose_name,
                                               mongo_name=mongo_name,
                                               **kwargs)
        self.validators.append(self.to_mongo)

    def to_mongo(self, value):
        if isinstance(value, OrderedDict):
            return value
        try:
            return OrderedDict(value)
        except ValueError as e:
            raise ValidationError(e)

    def to_python(self, value):
        try:
            return self.to_mongo(value)
        except ValidationError:
            return value


class ListField(MongoBaseField):
    """A field that stores a list."""
    def __init__(self, field=None, verbose_name=None, mongo_name=None,
                 **kwargs):
        """Create a new ListField.

        :parameters:
          - `field` The Field type representing all items in this list.
        """
        super(ListField, self).__init__(verbose_name=verbose_name,
                                        mongo_name=mongo_name,
                                        **kwargs)
        self._field = field

        def validate_items(items):
            if self._field:
                for item in items:
                    self._field.validate(item)
        self.validators.append(validate_items)

    def to_mongo(self, value):
        if self._field:
            return [self._field.to_mongo(v) for v in value]
        return value

    def to_python(self, value):
        if self._field:
            return [self._field.to_python(v) for v in value]
        return value

    def contribute_to_class(self, cls, name):
        super(ListField, self).contribute_to_class(cls, name)
        # Let inner fields know what model we're attached to.
        field = self._field
        while field is not None:
            field.model = self.model
            field = getattr(field, '_field', None)


#
# Geospatial field types.
#

class GeoJSONField(MongoBaseField):
    """Base class for GeoJSON fields."""

    def __init__(self, verbose_name=None, mongo_name=None, **kwargs):
        super(GeoJSONField, self).__init__(verbose_name=verbose_name,
                                           mongo_name=mongo_name,
                                           **kwargs)

        self.validators.append(self.validate_geojson)

    @classmethod
    def validate_geojson(cls, value):
        validators.validator_for_type(dict)(value)
        validators.validator_for_geojson_type(
            cls._geojson_name)(value)
        coordinates = value.get('coordinates')
        validators.validator_for_type(
            (list, tuple), 'Coordinates')(coordinates)
        cls.validate_coordinates(coordinates)

    def to_python(self, value):
        if isinstance(value, list):
            return {'type': self._geojson_name, 'coordinates': value}
        return value


class PointField(GeoJSONField):
    """A field that stores the GeoJSON 'Point' type.

    Values may be assigned to this field that are already in GeoJSON format, or
    you can assign a list that simply describes (longitude, latitude) in that
    order.

    """
    _geojson_name = 'Point'

    @staticmethod
    def validate_coordinates(coordinates):
        if not (isinstance(coordinates, (list, tuple)) and
                len(coordinates) == 2):
            raise ValidationError('Point is not a pair: %r' % coordinates)
        validate_number = validators.validator_for_type(
            (float, int), 'coordinate value')
        validate_number(coordinates[0])
        validate_number(coordinates[1])


class LineStringField(GeoJSONField):
    """A field that stores the GeoJSON 'LineString' type.

    Values may be assigned to this field that are already in GeoJSON format, or
    you can assign a list of coordinate points (each a list of two coordinates).

    """
    _geojson_name = 'LineString'

    @staticmethod
    def validate_coordinates(coordinates):
        try:
            coordinates[0][0]
        except Exception:
            raise ValidationError('LineString must contain at least one Point.')
        errors = []
        for point in coordinates:
            try:
                PointField.validate_coordinates(point)
            except ValidationError as e:
                errors.append(e)
        if errors:
            raise ValidationError(errors)


class PolygonField(GeoJSONField):
    """A field that stores the GeoJSON 'Polygon' type.

    Values may be assigned to this field that are already in GeoJSON format, or
    you can assign a list of LineStrings (each a list of Points).

    """
    _geojson_name = 'Polygon'

    @staticmethod
    def validate_coordinates(coordinates):
        try:
            coordinates[0][0][0]
        except Exception:
            raise ValidationError(
                'Polygons must contain at least one LineString.')
        errors = []
        for linestring in coordinates:
            try:
                LineStringField.validate_coordinates(linestring)
            except ValidationError as e:
                errors.append(e)
            else:
                if linestring[0] != linestring[-1]:
                    errors.append(ValidationError(
                        'LineString must start and end at the same Point: %r'
                        % linestring))
        if errors:
            raise ValidationError(errors)


class MultiPointField(GeoJSONField):
    """A field that stores the GeoJSON 'MultiPoint' type.

    Values may be assigned to this field that are already in GeoJSON format, or
    you can assign a list of Points (a list containing two coordinates).

    """
    _geojson_name = 'MultiPoint'

    @staticmethod
    def validate_coordinates(coordinates):
        try:
            coordinates[0][0]
        except Exception:
            raise ValidationError(
                'MultiPoint must contain at least one Point.')
        errors = []
        for point in coordinates:
            try:
                PointField.validate_coordinates(point)
            except ValidationError as e:
                errors.append(e)
        if errors:
            raise ValidationError(errors)


class MultiLineStringField(GeoJSONField):
    """A field that stores the GeoJSON 'MultiLineString' type.

    Values may be assigned to this field that are already in GeoJSON format, or
    you can assign a list of LineStrings (each a list of Points).

    """
    _geojson_name = 'MultiLineString'

    @staticmethod
    def validate_coordinates(coordinates):
        try:
            coordinates[0][0][0]
        except Exception:
            raise ValidationError(
                'MultiLineString must contain at least one LineString.')
        errors = []
        for linestring in coordinates:
            try:
                LineStringField.validate_coordinates(linestring)
            except ValidationError as e:
                errors.append(e)
        if errors:
            raise ValidationError(errors)


class MultiPolygonField(GeoJSONField):
    """A field that stores the GeoJSON 'MultiPolygonField' type.

    Values may be assigned to this field that are already in GeoJSON format, or
    you can assign a list of LineStrings (each a list of Points).

    """
    _geojson_name = 'MultiPolygon'

    @staticmethod
    def validate_coordinates(coordinates):
        try:
            coordinates[0][0][0][0]
        except Exception:
            raise ValidationError(
                'MultiPolygon must contain at least one Polygon.')
        errors = []
        for polygon in coordinates:
            try:
                PolygonField.validate_coordinates(polygon)
            except ValidationError as e:
                errors.append(e)
        if errors:
            raise ValidationError(errors)


class GeometryCollectionField(MongoBaseField):
    """A field that stores the GeoJSON 'GeometryCollection' type.

    Values may be assigned to this field that are already in GeoJSON format, or
    you can assign a list of geometries, where each geometry is a GeoJSON
    document.

    """
    _geo_field_classes = {
        'Point': PointField,
        'LineString': LineStringField,
        'Polygon': PolygonField,
        'MultiPoint': MultiPointField,
        'MultiLineString': MultiLineStringField,
        'MultiPolygon': MultiPolygonField,
    }

    def __init__(self, verbose_name=None, mongo_name=None, **kwargs):
        super(GeometryCollectionField, self).__init__(verbose_name=verbose_name,
                                                      mongo_name=mongo_name,
                                                      **kwargs)
        self.validators.append(
            validators.together(
                validators.validator_for_type(dict),
                validators.validator_for_geojson_type('GeometryCollection'),
                lambda value: validators.validator_for_type(
                    (list, tuple), 'Geometries')(value.get('geometries'))))
        self.validators.append(
            lambda value: self.validate_geometries(value.get('geometries')))

    @classmethod
    def validate_geometries(cls, geometries):
        if not geometries:
            raise ValidationError(
                'geometries must contain at least one geometry.')
        errors = []
        for geometry in geometries:
            geometry_type = geometry.get('type')
            field_class = cls._geo_field_classes.get(geometry_type)
            try:
                if field_class is None:
                    raise ValidationError(
                        'Invalid GeoJSON type: %s' % geometry_type)
                else:
                    field_class.validate_geojson(geometry)
            except ValidationError as e:
                errors.append(e)
        if errors:
            raise ValidationError(errors)

    def to_python(self, value):
        if isinstance(value, (list, tuple)):
            return {'type': 'GeometryCollection', 'geometries': value}
        return value


#
# RelatedModelField types.
#

class EmbeddedDocumentField(RelatedModelFieldsBase):

    """A field that stores a document inside another document."""

    def __init__(self, model,
                 verbose_name=None, mongo_name=None, **kwargs):
        super(EmbeddedDocumentField, self).__init__(model=model,
                                                    verbose_name=verbose_name,
                                                    mongo_name=mongo_name,
                                                    **kwargs)

        def validate_related_model(value):
            if not isinstance(value, self.related_model):
                raise ValidationError('value must be an instance of %s.'
                                      % (self.related_model.__name__))

        self.validators.append(validate_related_model)

    def to_python(self, value):
        if isinstance(value, dict):
            # Try to convert the value into our document type.
            return self.related_model.from_dict(value)
        return value

    def to_mongo(self, value):
        return value.to_son()


class EmbeddedDocumentListField(RelatedModelFieldsBase):
    """A field that stores a list of documents within a document.

    All documents in the list must be of the same type.
    """

    def __init__(self, model, verbose_name=None, mongo_name=None, **kwargs):
        super(EmbeddedDocumentListField, self).__init__(
            model=model,
            verbose_name=verbose_name,
            mongo_name=mongo_name,
            **kwargs)

        def validate_related_model(value):
            if not isinstance(value, list):
                raise ValidationError('%r must be a list.' % value)
            for v in value:
                if not isinstance(v, self.related_model):
                    raise ValidationError(
                        '%r is not an instance of %s.'
                        % (v, self.related_model.__name__))
                self.validators.append(validate_related_model)

    def to_python(self, value):
        return [self.related_model.from_dict(item)
                if isinstance(item, dict) else item
                for item in value]

    def to_mongo(self, value):
        return [doc.to_son() for doc in value]


class ReferenceField(RelatedModelFieldsBase):
    """A field that references another document within a document.

    Options for reference_delete_rule are as follows:

      * DO_NOTHING (0)  - don't do anything (default).
      * NULLIFY    (1)  - Updates the reference to null.
      * CASCADE    (2)  - Deletes the documents associated with the reference.
      * DENY       (3)  - Prevent the deletion of the reference object.
      * PULL       (4)  - Pull the reference from a
                          :class:`~pymodm.fields.ListField` of references
    """

    # Delete rules.
    DO_NOTHING = 0
    NULLIFY = 1
    CASCADE = 2
    DENY = 3
    PULL = 4

    def __init__(self, model, on_delete=DO_NOTHING,
                 verbose_name=None, mongo_name=None, **kwargs):
        super(ReferenceField, self).__init__(model=model,
                                             verbose_name=verbose_name,
                                             mongo_name=mongo_name,
                                             **kwargs)
        MongoModel = _import('pymodm.base.models.MongoModel')
        if (ReferenceField.DO_NOTHING != on_delete and
            not (isinstance(model, type) and
                 issubclass(model, MongoModel))):
            raise ValueError(
                'Cannot specify on_delete without providing a Model class '
                'for model (was: %r). For bidirectional delete rules, '
                'use MyModelClass.register_delete_rule instead.'
                % model)
        self._on_delete = on_delete
        self._is_instance = False

        def validate_related_model(ref):
            """Given a Model, verify that it's been saved first."""
            if isinstance(ref, self.related_model) and not ref.pk:
                raise ValidationError(
                    'Referenced documents must be saved to the database first.')

        self.validators.append(validate_related_model)

    def contribute_to_class(self, cls, name):
        super(ReferenceField, self).contribute_to_class(cls, name)
        # Install our delete rule on the class.
        if ReferenceField.DO_NOTHING != self._on_delete:
            self.related_model.register_delete_rule(self.model,
                                                    name,
                                                    self._on_delete)

    def to_python(self, value):
        if isinstance(value, dict):
            # Try to convert the value into our document type.
            return self.related_model.from_dict(value)
        elif isinstance(value, self.related_model):
            return value
        elif self.model._mongometa._auto_dereference:
            # Attempt to dereference the value as an id.
            dereference_id = _import('pymodm.dereference.dereference_id')
            return dereference_id(self.related_model, value)
        return value

    def to_mongo(self, value):
        if isinstance(value, self.related_model):
            if value._mongometa.pk.is_undefined(value):
                raise ValidationError(
                    'Referenced Models must be saved to the database first.')
            return value._mongometa.pk.to_mongo(value.pk)
        # Assume value is the _id.
        return value

    def __get__(self, inst, owner):
        MongoModelBase = _import('pymodm.base.models.MongoModelBase')
        if inst is not None and isinstance(inst, MongoModelBase):
            raw_value = inst._data.get(self.attname, self.default)
            if self.is_blank(raw_value):
                return raw_value
            python = self.to_python(raw_value)
            # Cache retrieved value.
            self.__set__(inst, python)
            return python
        return self

    def __set__(self, inst, value):
        MongoModel = _import('pymodm.base.models.MongoModel')
        super(ReferenceField, self).__set__(inst, value)
        self._is_instance = isinstance(value, MongoModel)
