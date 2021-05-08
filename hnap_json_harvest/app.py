import os
import json
import requests
import boto3
import smart_open
import datetime
import urllib.request
import xml.dom.minidom
from botocore.exceptions import ClientError
from xml.dom import minidom

def lambda_handler(event, context):
    """
    AWS Lambda Entry
    """
    print(event)
    
    #base_url = "https://maps.canada.ca/geonetwork"
    #gn_q_query = "/srv/eng/q"
    #gn_csw_url = "/srv/csw"
    #gn_change_api_url = "/srv/api/0.1/records/status/change"
    #gn_json_record_url = "/srv/api/0.1/records"
    
    base_url = "https://hnap-harv-bucket.s3.amazonaws.com"
    gn_q_query = "/q_xml.xml"
    #gn_csw_url = "/srv/csw"
    gn_change_api_url = "/change.json"
    #gn_json_record_url = "/srv/api/0.1/records"
    
    """ 
    Used for `sam local invoke -e payload.json` for local testing
    For actual use, comment out the two lines below 
    """
    
    if "body" in event:
        event = json.loads(event["body"])
        
    """ 
    Parse query string parameters 
    """
        
    try:
        runtype = event["queryStringParameters"]["runtype"]
    except:
        runtype = ""
        
    try:
        if datetime_valid(event["queryStringParameters"]["fromDateTime"]):
            fromDateTime = event["queryStringParameters"]["fromDateTime"]
        else:
            fromDateTime = False
    except:
        fromDateTime = False
    
    """ 
    Construct the body of the response object 
    """
    
    if runtype and fromDateTime:
        message = "Cannot use runtype and fromDateTime together"
    elif runtype == "full":
        message = "Reloading all JSON records..."
        uuid_list = get_full_uuids_list(base_url + gn_q_query)
        err_msg = harvest_uuids(uuid_list)
    elif fromDateTime:
        message = "Reloading all JSON records from: " + fromDateTime + "..."
    else:
        fromDateTime = datetime.datetime.utcnow().now() - datetime.timedelta(minutes=11)
        fromDateTime = fromDateTime.isoformat()[:-7] + 'Z'
        message = "Default setting. Harvesting JSON records from: " + fromDateTime + "..."
            
            
    response = {
        "statusCode": "200",
        "headers": {"Content-type": "application/json"},
        "body": json.dumps(
            {
                "statusCode": "200",
                "message": message,
                
            },
            indent = 4
        ),
    }
    return response

def datetime_valid(dt_str):
    #https://stackoverflow.com/a/61569783
    try:
        datetime.fromisoformat(dt_str)
    except:
        try:
            datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
        except:
            return False
        return True
    return True
    
def get_full_uuids_list(gn_q_query):
    """ Get a full list of all uuids """
    
    uuid_list = []
    
    try:
        str_data = urllib.request.urlopen(gn_q_query).read()
        xmldoc = minidom.parseString(str_data)
        
        metadatas = xmldoc.getElementsByTagName("metadata")
        print("XML has: %i metadata records" % len(metadatas))
        
        for metadata in metadatas:
            uuid = metadata.getElementsByTagName("uuid")[0]
            uuid_list.append(uuid.firstChild.data)
        
        return uuid_list
    except:
        #print("Could not load the GeoNetwork 3.6 'q' query. Cannot complete a full load of the dataset")
        #print("Could not access: ", gn_q_query)
        #return uuid_count
    
def get_changes(gn_change_api_url, fromDateTime):
    """ Returns a list of UUIDs to download """
    
def load_changes_records(, uuid_list, s3_bucket_name, s3_bucket_key):


def create_bucket(bucket_name, region=None):
    """Create an S3 bucket in a specified region

    If a region is not specified, the bucket is created in the S3 default
    region (us-east-1).

    :param bucket_name: Bucket to create
    :param region: String region to create bucket in, e.g., 'us-west-2'
    :return: True if bucket created, else False
    """

    # Create bucket
    try:
        if region is None:
            s3_client = boto3.client('s3')
            s3_client.create_bucket(Bucket=bucket_name)
        else:
            s3_client = boto3.client('s3', region_name=region)
            location = {'LocationConstraint': region}
            s3_client.create_bucket(Bucket=bucket_name,
                                    CreateBucketConfiguration=location)
    except ClientError as e:
        logging.error(e)
        return False
    return True

def upload_file(file_name, bucket, object_name=None):
    """Upload a file to an S3 bucket

    :param file_name: File to upload
    :param bucket: Bucket to upload to
    :param object_name: S3 object name. If not specified then file_name is used
    :return: True if file was uploaded, else False
    """

    # If S3 object_name was not specified, use file_name
    if object_name is None:
        object_name = file_name

    # Upload the file
    s3_client = boto3.client('s3')
    try:
        response = s3_client.upload_file(file_name, bucket, object_name)
    except ClientError as e:
        logging.error(e)
        return False
    return True

def harvest_uuids(uuid_list, gn_json_record_url, s3_bucket_name, s3_bucket_key):
    """ Harvests GeoNetwork JSON file into s3_bucket_name """
    """ Ensure s3_bucket_key is saved as aws environment variable """
    
    return True