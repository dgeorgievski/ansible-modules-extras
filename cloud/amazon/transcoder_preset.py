#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# This is a free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This Ansible library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this library.  If not, see <http://www.gnu.org/licenses/>.

DOCUMENTATION = '''
module: transcoder_preset
short_description: Manage AWS ElasticTranscoder presets
version_added: "2.1.1"
description:
  - Create or delete ElasticTranscoder Presets. Preset will be created only if one with the specified name does not exist.
    If recreate option is set to true, the existing preset will be deleted first, and then created again.

    Please note, preset names are not unique in AWS, but their Id-s are. This module is using using the preset names to manage them in AWS, and maintain their uniqness.
    Arguably, the preset names are easier for humans (read developers) to refer to, especialy when one needs to work with the same presets accross different AWS accounts.

    For more detils see U(http://docs.aws.amazon.com/elastictranscoder/latest/developerguide/working-with-presets.html)

author: Dimitar Georgievski, @dgeorgievski
requirements:
  - "boto3 >= 1.3.0"
  - "json >= 2.0.9"
options:
    name:
        description:
            - Name of the preset.
        required: False
    description:
        description:
            - Description of the preset.
        required: False
    state:
        description:
            - Create or delete the preset
        required: false
        choices: ['present', 'absent']
        default: 'present'
    recreate:
        description
            - If set to true and state equals to present, recreate the preset by deleting it first.
              Unfortunately, presets could not be updated in AWS.
        required: False
        choices: [true, false]
        default: false
    container:
        description:
            - The  container  type  for  the output file
        choices: ['flac', 'flv', 'fmp4', 'gif', 'mp3', 'mp4', 'mpg', 'mxf', 'oga', 'ogg', 'ts', 'webm']
        required: true
        default: None
    preset_document:
        description:
            - Path to a json document that defines the preset template. The templace could have video, audio and/or thumbnails sections.
        required: False
        default: None

'''

EXAMPLES = '''

- name: Create Preset
  transcoder_preset:
    name: "test_300_sd_video"
    description: "Preset test"
    container: "mp4"
    preset_document: "roles/cloudformation/files/example_preset_video.json"

- name: Recreate Preset
  transcoder_preset:
    name: "test_300_sd_video"
    description: "Preset test"
    container: "mp4"
    recreate: true
    preset_document: "roles/cloudformation/files/example_preset_video.json"

- name: Delete Preset
  transcoder_preset:
    name: "test_300_sd_video"
    state: absent

    Where the template's JSON format is:
    {
      "Container": "mp4",
      "Name": "test_600_sd",
      "Type": "Custom",
      "Video": { ... },
      "Audio": { ... },
      "Thumbnails": { ... },
     }
'''

RETURN = '''
name:
    description: Preset's Name
    returned: success
    type: string
    sample: "test_300_sd_video"
id:
    description: Preset's Id
    returned: success
    type: string
    sample: "1466672939342-kdjcje"
arn:
    description: Preset's Arn
    returned: success
    type: string
    sample: "arn:aws:elastictranscoder:us-east-1:123456789012:preset/1466672939342-kdjcje"
msg:
    description: Result of action
    returned: success
    type: string
    sample: "Preset created successfully"
'''
import json

try:
    import boto3
    from  botocore.exceptions import ClientError
    HAS_BOTO3 = True
except ImportError:
    HAS_BOTO3 = False


def get_preset_id(client, preset_name):

    paginator = client.get_paginator('list_presets')

    operation_parameters = {'Ascending': 'true'}

    page_iterator = paginator.paginate(**operation_parameters)
    for page in page_iterator:
        next_token = page.get('NextPageToken', None)
        if 'Presets' in page.keys():
            for preset in page['Presets']:
                if preset['Name'] == preset_name:
                    return preset['Id'], preset['Arn']

        if next_token is None:
            break
        else:
            operation_parameters['PageToken'] = next_token

    return None, None


def delete_preset_by_id(client, preset_name, preset_id):

    try:
        client.delete_preset(Id=preset_id)
    except botocore.exceptions.ClientError, e:
        module.fail_json(msg="Failed to delete preset {0}/{1}: {2}".format(preset_name, preset_id, str(e)))


def create_preset(client, module):

    params = dict()
    PresetName = None
    PresetId = None
    PresetArn = None
    result = {'name': '',
              'id': '',
              'arn': '',
              'msg': ''}

    if module.params.get('name'):
        PresetName = params['Name'] = module.params.get('name')
    else:
        module.fail_json(msg="Missing required argument: name")

    recreate = False
    if module.params.get('recreate'):
        recreate = module.params.get('recreate')

    PresetId, PresetArn = get_preset_id(client, PresetName)

    if (PresetId
        and not recreate):
        result['name'] = PresetName
        result['id'] = PresetId
        result['arn'] = PresetArn
        result['msg'] = "Preset already exists"
        return result

    if (PresetId
        and recreate):
        delete_preset_by_id(client, PresetName, PresetId)

    if module.params.get('description'):
        params['Description'] = module.params.get('description')

    if module.params.get('container'):
        params['Container']=module.params.get('container')
    else:
        module.fail_json(msg = "Missing required argument: container")

    PresetTemplate = {}
    if module.params.get('preset_document'):
        spec_path = module.params.get('preset_document')
        if not os.path.isfile(spec_path):
            module.fail_json(msg = "Wrong path for preset_document: {0}".format(spec_path))

        try:
            with open(spec_path) as f:
                PresetTemplate = json.load(f)
        except IOError, e:
            module.fail_json(msg = "Can't open video_template file - " + str(e))

    if 'Video' in PresetTemplate:
        params['Video'] = PresetTemplate['Video']

    if 'Audio' in PresetTemplate:
        params['Audio'] = PresetTemplate['Audio']

    if 'Thumbnails' in PresetTemplate:
        params['Thumbnails'] = PresetTemplate['Thumbnails']

    if (len(params['Video']) == 0 and
        len(params['Audio']) == 0 and
        len(params['Thumbnails']) == 0):
        module.fail_json(msg="No specs provided for Video, Audio, or Thumbnails. ")

    if not module.check_mode:
        try:
            create_result = client.create_preset(**params)
            result['name'] = create_result['Preset']['Name']
            result['id'] = create_result['Preset']['Id']
            result['arn'] = create_result['Preset']['Arn']
        except botocore.exceptions.ClientError, e:
            module.fail_json(msg="Invalid preset settings: " + str(e))

    result['msg'] = 'Preset created successfully'
    result['changed'] = 'true'

    return result

def delete_preset(client, module):
    params = dict()
    PresetName = None
    PresetId = None
    PresetArn = None
    result = {'name':'',
            'id': '',
            'arn': '',
            'msg':''}

    if module.params.get('name'):
        PresetName = params['Name'] = module.params.get('name')
    else:
        module.fail_json(msg="Missing required argument: name")

    PresetId, PresetArn = get_preset_id(client, PresetName)

    result['msg'] = 'Preset deleted successfully'
    result['changed'] = 'true'

    if PresetId:
        result['id'] = PresetId
        result['arn'] = PresetArn

        if not module.check_mode:
            try:
                client.delete_preset(Id=PresetId)
            except botocore.exceptions.ClientError, e:
                module.fail_json(msg="Failed to delete preset {0}: {1}".format(PresetName,  e))

    else:
        if not module.check_mode:
            result['msg'] = 'Preset not found'
            result['changed'] = 'false'

    result['name'] = PresetName

    return result

def main():
    argument_spec = ec2_argument_spec()
    argument_spec.update(dict(
        name = dict(type='str', required=True),
        description = dict(type='str'),
        container = dict(
            type='str',
            default=None,
            choices=[
                'flac',
                'flv',
                 'fmp4',
                 'gif',
                 'mp3',
                 'mp4',
                 'mpg',
                 'mxf',
                 'oga',
                 'ogg',
                 'ts',
                 'webm']),
        state = dict(
            type='str',
            default='present',
            choices=['present', 'absent']),
        recreate = dict(
            type='bool',
            default=False,
            choices=[True, False]),
        preset_document = dict(type='str')
        )
    )

    module = AnsibleModule(argument_spec=argument_spec,
                           supports_check_mode=True)

    if not HAS_BOTO3:
        module.fail_json(msg='boto3 required for this module')

    try:
        region, ec2_url, aws_connect_kwargs = get_aws_connection_info(module, boto3=True)
        transcoder = boto3_conn(module, conn_type='client', resource='elastictranscoder', region=region, endpoint=ec2_url, **aws_connect_kwargs)
    except boto.exception.NoAuthHandlerFound, e:
        module.fail_json(msg="Can't authorize connection - "+str(e))

    invocations = {
        'present': create_preset,
        'absent': delete_preset,
    }
    results = invocations[module.params.get('state')](transcoder, module)

    module.exit_json(**results)

# import module snippets
from ansible.module_utils.basic import *
from ansible.module_utils.ec2 import *

if __name__ == '__main__':
    main()
