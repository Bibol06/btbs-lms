"""Run in authorized AWS CloudShell after the reviewed stack is complete."""
import json
import boto3
from botocore.exceptions import ClientError

s = boto3.client('s3', region_name='eu-north-1')
b = 'btbs-lms-media-506546664509-eu-north-1'
stack = boto3.client('cloudformation', region_name='eu-north-1').describe_stacks(StackName='btbs-private-media')['Stacks'][0]
assert stack['StackStatus'] == 'CREATE_COMPLETE'
o = {i['OutputKey']: i['OutputValue'] for i in stack['Outputs']}
try:
    p = json.loads(s.get_bucket_policy(Bucket=b)['Policy'])
except ClientError as e:
    if e.response['Error']['Code'] != 'NoSuchBucketPolicy':
        raise
    p = {'Version': '2012-10-17', 'Statement': []}
with open('btbs-policy-before-final.json', 'x') as f:
    json.dump(p, f)
p['Statement'] = [x for x in p['Statement'] if x.get('Sid') != 'BtbsCloudFrontRead'] + [json.loads(o['BucketPolicyStatement'])]
s.put_bucket_policy(Bucket=b, Policy=json.dumps(p))
print('CloudFront private access configured.')
print('Backup versioning:', s.get_bucket_versioning(Bucket=o['BackupBucket'])['Status'])
print('Backup public access blocked:', all(s.get_public_access_block(Bucket=o['BackupBucket'])['PublicAccessBlockConfiguration'].values()))
print('CloudFront status:', boto3.client('cloudfront').get_distribution(Id=o['DistributionId'])['Distribution']['Status'])
