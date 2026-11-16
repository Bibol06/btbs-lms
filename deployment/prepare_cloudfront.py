"""Create a local signing key and a reviewable CloudFormation template, not AWS resources."""
import json
from pathlib import Path
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

root = Path(__file__).resolve().parents[1]
private = root / '.local' / 'cdn' / 'signing-key.pem'
private.parent.mkdir(parents=True, exist_ok=True)
if private.exists():
    key = serialization.load_pem_private_key(private.read_bytes(), password=None)
else:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    with private.open('xb') as stream:
        stream.write(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    private.chmod(0o600)
public = key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
ref = lambda name: {'Ref': name}
sub = lambda value: {'Fn::Sub': value}
template = {
 'AWSTemplateFormatVersion': '2010-09-09',
 'Description': 'BTBS private media CDN. Merge output statement into existing S3 policy separately.',
 'Parameters': {'BucketName': {'Type': 'String'}, 'BucketRegion': {'Type': 'String', 'Default': 'eu-north-1'}},
 'Resources': {
  'SigningKey': {'Type': 'AWS::CloudFront::PublicKey', 'Properties': {'PublicKeyConfig': {'CallerReference': sub('${AWS::StackName}-key'), 'Name': sub('${AWS::StackName}-key'), 'EncodedKey': public}}},
  'KeyGroup': {'Type': 'AWS::CloudFront::KeyGroup', 'Properties': {'KeyGroupConfig': {'Name': sub('${AWS::StackName}-keys'), 'Items': [ref('SigningKey')]}}},
  'OriginAccess': {'Type': 'AWS::CloudFront::OriginAccessControl', 'Properties': {'OriginAccessControlConfig': {'Name': sub('${AWS::StackName}-s3'), 'OriginAccessControlOriginType': 's3', 'SigningBehavior': 'always', 'SigningProtocol': 'sigv4'}}},
  'MediaCache': {'Type': 'AWS::CloudFront::CachePolicy', 'Properties': {'CachePolicyConfig': {'Name': sub('${AWS::StackName}-media'), 'DefaultTTL': 3600, 'MinTTL': 60, 'MaxTTL': 86400,
   'ParametersInCacheKeyAndForwardedToOrigin': {'CookiesConfig': {'CookieBehavior': 'none'}, 'HeadersConfig': {'HeaderBehavior': 'none'}, 'QueryStringsConfig': {'QueryStringBehavior': 'none'}, 'EnableAcceptEncodingGzip': False, 'EnableAcceptEncodingBrotli': False}}}},
  'Distribution': {'Type': 'AWS::CloudFront::Distribution', 'Properties': {'DistributionConfig': {
   'Enabled': True, 'Comment': 'BTBS private course media', 'PriceClass': 'PriceClass_100', 'HttpVersion': 'http2',
   'Origins': [{'Id': 'MediaS3', 'DomainName': sub('${BucketName}.s3.${BucketRegion}.amazonaws.com'), 'OriginPath': '/_s3', 'OriginAccessControlId': ref('OriginAccess'), 'S3OriginConfig': {'OriginAccessIdentity': ''}}],
   'DefaultCacheBehavior': {'TargetOriginId': 'MediaS3', 'ViewerProtocolPolicy': 'https-only', 'AllowedMethods': ['GET','HEAD'], 'CachedMethods': ['GET','HEAD'], 'TrustedKeyGroups': [ref('KeyGroup')], 'CachePolicyId': ref('MediaCache'), 'Compress': False},
   'ViewerCertificate': {'CloudFrontDefaultCertificate': True}}}},
 },
 'Outputs': {'Domain': {'Value': {'Fn::GetAtt': ['Distribution','DomainName']}}, 'KeyId': {'Value': ref('SigningKey')}, 'DistributionId': {'Value': ref('Distribution')},
  'BucketPolicyStatement': {'Value': sub('{"Sid":"BtbsCloudFrontRead","Effect":"Allow","Principal":{"Service":"cloudfront.amazonaws.com"},"Action":"s3:GetObject","Resource":"arn:aws:s3:::${BucketName}/_s3/*","Condition":{"StringEquals":{"AWS:SourceArn":"arn:aws:cloudfront::${AWS::AccountId}:distribution/${Distribution}"}}}')}}
}
template['Resources']['Backups'] = {
 'Type': 'AWS::S3::Bucket', 'DeletionPolicy': 'Retain', 'UpdateReplacePolicy': 'Retain',
 'Properties': {'BucketName': sub('btbs-lms-backups-${AWS::AccountId}-${AWS::Region}'),
  'PublicAccessBlockConfiguration': {'BlockPublicAcls': True, 'IgnorePublicAcls': True, 'BlockPublicPolicy': True, 'RestrictPublicBuckets': True},
  'OwnershipControls': {'Rules': [{'ObjectOwnership': 'BucketOwnerEnforced'}]},
  'VersioningConfiguration': {'Status': 'Enabled'},
  'BucketEncryption': {'ServerSideEncryptionConfiguration': [{'ServerSideEncryptionByDefault': {'SSEAlgorithm': 'AES256'}}]},
  'LifecycleConfiguration': {'Rules': [{'Id': 'EncryptedArchiveRetention', 'Status': 'Enabled', 'Prefix': 'encrypted/',
     'ExpirationInDays': 30, 'NoncurrentVersionExpiration': {'NoncurrentDays': 7}, 'AbortIncompleteMultipartUpload': {'DaysAfterInitiation': 1}}]}}}
template['Resources']['BackupTLS'] = {'Type': 'AWS::S3::BucketPolicy', 'Properties': {
 'Bucket': ref('Backups'), 'PolicyDocument': {'Version': '2012-10-17', 'Statement': [{
  'Sid': 'RequireTLS', 'Effect': 'Deny', 'Principal': '*', 'Action': 's3:*',
  'Resource': [sub('arn:aws:s3:::${Backups}'), sub('arn:aws:s3:::${Backups}/*')],
  'Condition': {'Bool': {'aws:SecureTransport': 'false'}}}]}}}
template['Resources']['StorageAdditions'] = {'Type': 'AWS::IAM::Policy', 'Properties': {
 'PolicyName': 'BtbsMultipartAndEncryptedBackups', 'Users': ['btbs-lms-storage'],
 'PolicyDocument': {'Version': '2012-10-17', 'Statement': [
  {'Sid': 'ResumeOwnMedia', 'Effect': 'Allow', 'Action': ['s3:AbortMultipartUpload', 's3:ListMultipartUploadParts'], 'Resource': sub('arn:aws:s3:::${BucketName}/_staging/*')},
  {'Sid': 'EncryptedBackupsNoDelete', 'Effect': 'Allow', 'Action': ['s3:PutObject','s3:GetObject','s3:GetObjectVersion','s3:AbortMultipartUpload','s3:ListMultipartUploadParts'], 'Resource': sub('arn:aws:s3:::${Backups}/encrypted/*')}
 ]}}}
template['Outputs']['BackupBucket'] = {'Value': ref('Backups')}
out = root/'deployment'/'cloudfront-private.json'
out.write_text(json.dumps(template, indent=2)+'\n', encoding='utf-8')
print('Private key retained locally; public-key-only template prepared:', out)
