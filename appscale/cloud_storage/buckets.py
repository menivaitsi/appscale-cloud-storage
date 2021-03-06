import json

from boto.exception import S3ResponseError
from flask import request
from flask import Response
from flask import url_for
from .constants import HTTP_CONFLICT
from .constants import HTTP_NO_CONTENT
from .constants import HTTP_NOT_FOUND
from .constants import HTTP_NOT_IMPLEMENTED
from .decorators import assert_required
from .decorators import assert_unsupported
from .decorators import authenticate
from .utils import error
from .utils import index_bucket
from .utils import query_buckets


@authenticate
@assert_unsupported('maxResults', 'pageToken', 'prefix')
@assert_required('project')
def list_buckets(project, conn):
    """ Retrieves a list of buckets for the given project. """
    projection = request.args.get('projection') or 'noAcl'
    if projection != 'noAcl':
        return error('projection: {} not supported.'.format(projection),
                     HTTP_NOT_IMPLEMENTED)

    index = query_buckets(project)

    response = {'kind': 'storage#buckets'}
    buckets = tuple(bucket for bucket in conn.get_all_buckets()
                    if bucket.name in index)
    if not buckets:
        return json.dumps(response)

    items = []
    for bucket in buckets:
        bucket_url = url_for('get_bucket', bucket_name=bucket.name)
        items.append({
            'kind': 'storage#bucket',
            'id': bucket.name,
            'selfLink': request.url_root[:-1] + bucket_url,
            'name': bucket.name,
            'timeCreated': bucket.creation_date
        })
    response['items'] = items

    return Response(json.dumps(response), mimetype='application/json')


@authenticate
@assert_unsupported('predefinedAcl', 'predefinedDefaultObjectAcl',
                    'projection')
@assert_required('project')
def insert_bucket(project, conn):
    """ Creates a new bucket. """
    bucket_info = request.get_json()
    # TODO: Do the following lookup and create under a lock.
    if conn.lookup(bucket_info['name']) is not None:
        return error('Sorry, that name is not available. '
                     'Please try a different one.', HTTP_CONFLICT)

    index_bucket(bucket_info['name'], project)

    conn.create_bucket(bucket_info['name'])

    # The HEAD bucket request does not return creation_date. This is an
    # inefficient way of retrieving it.
    try:
        bucket = next(bucket for bucket in conn.get_all_buckets()
                      if bucket.name == bucket_info['name'])
    except StopIteration:
        return error('Unable to find bucket after creating it.')

    bucket_url = url_for('get_bucket', bucket_name=bucket.name)
    response = {
        'kind': 'storage#bucket',
        'id': bucket.name,
        'selfLink': request.url_root[:-1] + bucket_url,
        'name': bucket.name,
        'timeCreated': bucket.creation_date,
        'updated': bucket.creation_date
    }
    return Response(json.dumps(response), mimetype='application/json')


@authenticate
@assert_unsupported('ifMetagenerationMatch', 'ifMetagenerationNotMatch',
                    'fields')
def get_bucket(bucket_name, conn):
    """ Returns metadata for the specified bucket. """
    projection = request.args.get('projection') or 'noAcl'
    if projection != 'noAcl':
        return error('projection: {} not supported.'.format(projection),
                     HTTP_NOT_IMPLEMENTED)

    try:
        bucket = next(bucket for bucket in conn.get_all_buckets()
                      if bucket.name == bucket_name)
    except StopIteration:
        return error('Not Found', HTTP_NOT_FOUND)

    bucket_url = url_for('get_bucket', bucket_name=bucket.name)
    response = {
        'kind': 'storage#bucket',
        'id': bucket.name,
        'selfLink': request.url_root[:-1] + bucket_url,
        'name': bucket.name,
        'timeCreated': bucket.creation_date,
        'updated': bucket.creation_date
    }
    return Response(json.dumps(response), mimetype='application/json')


@authenticate
@assert_unsupported('ifMetagenerationMatch', 'ifMetagenerationNotMatch')
def delete_bucket(bucket_name, conn):
    """ Deletes an empty bucket. """
    try:
        bucket = conn.get_bucket(bucket_name)
    except S3ResponseError:
        return error('Not Found', HTTP_NOT_FOUND)

    try:
        bucket.delete()
    except S3ResponseError:
        return error('The bucket you tried to delete was not empty.',
                     HTTP_CONFLICT)

    return '', HTTP_NO_CONTENT
