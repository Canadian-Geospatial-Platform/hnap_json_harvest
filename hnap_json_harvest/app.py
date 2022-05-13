import os
import json
import requests
import boto3
import smart_open
import urllib.request
import xml.dom.minidom
import logging
import datetime
import boto3.exceptions

from botocore.exceptions import ClientError
from xml.dom import minidom

BUCKET_NAME = os.environ['BUCKET_NAME']
BASE_URL = os.environ['BASE_URL']
GN_JSON_RECORD_URL_START = os.environ['GN_JSON_RECORD_URL_START']
RUN_INTERVAL_MINUTES = os.environ['RUN_INTERVAL_MINUTES']

def lambda_handler(event, context):
    """
    AWS Lambda Entry
    """
    #print(event)
    
    """PROD SETTINGS"""    
    #base_url = "https://maps.canada.ca"
    #gn_json_record_url_start = "https://maps.canada.ca/geonetwork/srv/api/0.1/records/"
    
    base_url = BASE_URL
    gn_change_api_url = "/geonetwork/srv/api/0.1/records/status/change"    
    gn_json_record_url_start = GN_JSON_RECORD_URL_START
    gn_json_record_url_end = "/formatters/json?addSchemaLocation=true&attachment=false&withInfo=false" #other flags: increasePopularity
    bucket_location = "ca-central-1"
    bucket = BUCKET_NAME #redacted
    err_msg = None
	
    try:
        run_interval_minutes = int(RUN_INTERVAL_MINUTES)
        if run_interval_minutes == None or run_interval_minutes == "":
            run_interval_minutes = 11
    except:
	    run_interval_minutes = 11

    """ 
    Parse query string parameters 
    """
    
    try:
        verbose = event["queryStringParameters"]["verbose"]
    except:
        verbose = False
        
    try:
        runtype = event["queryStringParameters"]["runtype"]
        if runtype == "uuid":
            try:
                uuid = event["queryStringParameters"]["uuid"]
            except:
                uuid = False
    except:
        runtype = False
        
    try:
        if datetime_valid(event["queryStringParameters"]["fromDateTime"]):
            fromDateTime = event["queryStringParameters"]["fromDateTime"]
        else:
            fromDateTime = False
    except:
        fromDateTime = False
    
    #toDateTime
    try:
        if datetime_valid(event["queryStringParameters"]["toDateTime"]):
            toDateTime = event["queryStringParameters"]["toDateTime"]
        else:
            toDateTime = False
    except:
        toDateTime = False
        

    
    """ 
    Construct the body of the response object 
    """
    
    if runtype and fromDateTime:
        message = "Cannot use runtype and fromDateTime together"
    elif runtype == "uuid" and uuid:
        message = "Reloading a list of JSON records..."
        uuid_list = [uuid]
    elif fromDateTime and toDateTime:
        message = "Reloading JSON records from: " + fromDateTime + " to" + toDateTime + "..."
        uuid_list,uuid_deleted_list = get_fromtoDateTime_uuids_list(base_url + gn_change_api_url, fromDateTime, toDateTime)
    elif fromDateTime:
        message = "Reloading JSON records from: " + fromDateTime + "..."
        uuid_list,uuid_deleted_list = get_fromDateTime_uuids_list(base_url + gn_change_api_url, fromDateTime)
    elif toDateTime:
        message = "Reloading JSON records to: " + toDateTime + "..."
        uuid_list, uuid_deleted_list = get_toDateTime_uuids_list(base_url + gn_change_api_url, toDateTime)
    else:
        fromDateTime = datetime.datetime.utcnow().now() - datetime.timedelta(minutes=run_interval_minutes)
        fromDateTime = fromDateTime.isoformat()[:-7] + 'Z'
        message = "Default setting. Harvesting JSON records from: " + fromDateTime + "..."
        uuid_list = get_fromDateTime_uuids_list(base_url + gn_change_api_url, fromDateTime)
    
    if len(uuid_list) > 0:
        err_msg = harvest_uuids(uuid_list, gn_json_record_url_start, gn_json_record_url_end, bucket, bucket_location)
    
    if len(uuid_deleted_list) > 0:
        err_msg_2 = delete_uuids(uuid_deleted_list, bucket)
        
    if not err_msg and not err_msg_2:
        message += "..." + str(len(uuid_list)) + " record(s) harvested into " + bucket
        message += "..." + str(len(uuid_deleted_list)) + " record(s) deleted from " + bucket
        if verbose == "true" and len(uuid_list) >0:
            message += '"uuid": ['
            for i in range(len(uuid_list)):
                #JSON format does not allow trailing commas for the last item of an array
                #See: https://www.json.org/json-en.html
                #Append comma if not the first element 
                if i:
                    message += ","
                message += "{" + uuid_list[i] + "}"
            message += "]"
    else:
        message += "... some error occured:" + err_msg
            
    response = {
        "statusCode": "200",
        "headers": {"Content-type": "application/json"},
        "body": json.dumps(
            {
                "fromDateTime": fromDateTime,
                "harvestCount": str(len(uuid_list)),
                "message": message,
            }
        ),
    }
    return response

def datetime_valid(dt_str):
    """
    Check to see if user supplied a valid datetime 
    in ISO:8601 UTC time with +00:00 or 'Z' 
    https://stackoverflow.com/a/61569783
    
    """
    try:
        datetime.datetime.fromisoformat(dt_str)
    except:
        try:
            datetime.datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
        except:
            print("fromDateTime is not a valid ISO:8601 UTC datetime with +00:00 or 'Z' ")
            return False
        return True
    return True
    
def convert_to_datetime(dt_str):
    """
    Check to see if user supplied a valid datetime and returns it as a datetime object
    in ISO:8601 UTC time with +00:00 or 'Z' 
    https://stackoverflow.com/a/61569783
    
    """
    
    try:
        dt_str = datetime.datetime.fromisoformat(dt_str)
    except:
        try:
            dt_str = datetime.datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
        except:
            print("fromDateTime is not a valid ISO:8601 UTC datetime with +00:00 or 'Z' ")
            return False
        return dt_str
    return dt_str
    
def get_toDateTime_uuids_list(gn_change_query, toDateTime):
    """ Get a list of insert/deleted/modified uuids from toDateTime
    :param gn_change_query: URL of the GeoNetwork change api
    :param toDateTime: datetime of when to harvest
    :return: a list of uuids to harvest
    """
    
    uuid_list = []
    uuid_deleted_list=[]
    
    try:
        #Use the build in toDateTime functionality in the GN change API
        gn_change_filter = "dateTo=" + toDateTime
        gn_change_query = gn_change_query + "?" + gn_change_filter
        #print (gn_change_query)

        headers = { 
                "Content-Type": "application/json; charset=utf-8",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            }
        response = requests.get(gn_change_query, headers=headers)
        str_data = json.loads(response.text)

        for metadata in str_data['records']:
            lastdatetime = metadata['lastModifiedTime']
            modification = metadata['status']
            if convert_to_datetime(lastdatetime) <= convert_to_datetime(toDateTime) and modification != 'deleted':
                #print(metadata['uuid'])
                uuid = metadata['uuid']
                uuid_list.append(uuid)
                
            elif convert_to_datetime(lastdatetime) <= convert_to_datetime(toDateTime) and modification == 'deleted':
                uuid = metadata['uuid']
                uuid_deleted_list.append(uuid)
            
        print("Using the toDateTime provided: %s, there are: %i metadata records to harvest" % (toDateTime, len(uuid_list)))
        print("Using the toDateTime provided: %s, there are: %i metadata records are deleted " % (toDateTime, len(uuid_deleted_list)))    
        return uuid_list, uuid_deleted_list
    except:
        print("Could not load the GeoNetwork 3.6 change api.")
        print("Cannot complete a load of the dataset")
        print("Could not access or properly parse: ", gn_change_query)
        error_msg = "Could not access or properly parse: " + gn_change_query
        return error_msg
        
def get_fromDateTime_uuids_list(gn_change_query, fromDateTime):
    """ Get a list of insert/deleted/modified uuids from fromDateTime
    :param gn_change_query: URL of the GeoNetwork change api
    :param fromDateTime: datetime of when to harvest
    :return: a list of uuids to harvest
    """
    
    uuid_list = []
    uuid_deleted_list = []
    
    try:
        #Use the build in fromDateTime functionality in the GN change API
        gn_change_filter = urllib.parse.quote("dateFrom=" + fromDateTime)
        gn_change_query = gn_change_query + "?" + gn_change_filter
        print (gn_change_query)
   
        ###requests
        headers = { 
                "Content-Type": "application/json; charset=utf-8",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            }
        response = requests.get(gn_change_query, headers=headers)
        str_data = json.loads(response.text)

        for metadata in str_data['records']:
            lastdatetime = metadata['lastModifiedTime']
            modification = metadata['status']
            if convert_to_datetime(lastdatetime) >= convert_to_datetime(fromDateTime) and modification != 'deleted':
                #print(metadata['uuid'])
                uuid = metadata['uuid']
                uuid_list.append(uuid)
            elif convert_to_datetime(lastdatetime) >= convert_to_datetime(fromDateTime) and modification == 'deleted':
                uuid = metadata['uuid']
                uuid_deleted_list.append(uuid)
            
        print("Using the fromDateTime provided: %s, there are: %i metadata records to harvest" % (fromDateTime, len(uuid_list)))
        print("Using the fromDateTime provided: %s, there are: %i metadata records are deleted" % (fromDateTime, len(uuid_deleted_list)))
        
        return uuid_list, uuid_deleted_list
    except:
        print("Could not load the GeoNetwork 3.6 change api.")
        print("Cannot complete a load of the dataset")
        print("Could not access or properly parse: ", gn_change_query)
        error_msg = "Could not access or properly parse: " + gn_change_query
        return error_msg
        
def get_fromtoDateTime_uuids_list(gn_change_query, fromDateTime, toDateTime):
    """ Get a list of insert/deleted/modified uuids from fromDateTime to toDateTime
    :param gn_change_query: URL of the GeoNetwork change api
    :param fromDateTime: lower datetime of when to harvest
    :param toDateTime: upper datetime of when to harvest
    :return: a list of uuids to harvest
    """
    
    uuid_list = []
    uuid_deleted_list = []
    
    try:
        #Use the build in toDateTime functionality in the GN change API
        gn_change_filter = "dateFrom=" + fromDateTime + "&dateTo=" + toDateTime
        gn_change_query = gn_change_query + "?" + gn_change_filter
        #print (gn_change_query)

        headers = { 
                "Content-Type": "application/json; charset=utf-8",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            }
        response = requests.get(gn_change_query, headers=headers)
        str_data = json.loads(response.text)

        for metadata in str_data['records']:
            lastdatetime = metadata['lastModifiedTime']
            modification = metadata['status']
            if (convert_to_datetime(lastdatetime) <= convert_to_datetime(toDateTime) and 
                convert_to_datetime(lastdatetime) >= convert_to_datetime(fromDateTime) and 
                modification != 'deleted'):
                #print(metadata['uuid'])
                uuid = metadata['uuid']
                uuid_list.append(uuid)
            elif (convert_to_datetime(lastdatetime) <= convert_to_datetime(toDateTime) and 
                convert_to_datetime(lastdatetime) >= convert_to_datetime(fromDateTime) and 
                modification == 'deleted'): 
                uuid = metadata['uuid']
                uuid_deleted_list.append(uuid)
            
        print("Using the toDateTime and fromDateTime provided, there are: %i metadata records to harvest" % (len(uuid_list)))
        print("Using the toDateTime and fromDateTime provided, there are: %i metadata records are deleted" % (len(uuid_deleted_list)))
        return uuid_list, uuid_deleted_list
    except:
        print("Could not load the GeoNetwork 3.6 change api.")
        print("Cannot complete a load of the dataset")
        print("Could not access or properly parse: ", gn_change_query)
        error_msg = "Could not access or properly parse: " + gn_change_query
        return error_msg
    
def create_bucket(bucket_name, region=None):
    """Create an S3 bucket in a specified region

    If a region is not specified, the bucket is created in the S3 default
    region (us-east-1).

    :param bucket_name: Bucket to create
    :param region: String region to create bucket in, e.g., 'us-west-2'
    :return: True if bucket created, else False
    """
    
    
    client = boto3.client('s3', region_name=region)
    response = client.head_bucket(Bucket=bucket_name)
    if response['ResponseMetadata']['HTTPStatusCode'] == 200:
        """ Bucket already exists and we have sufficent permissions """
        print("Bucket already exists and we have sufficent permissions")
        return True
    else:
        """" Create bucket """
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
        return True #Success

def upload_json_stream(file_name, bucket, json_data, object_name=None):
    """Upload a json file to an S3 bucket

    :param file_name: File to upload
    :param bucket: Bucket to upload to
    :param json_data: stream of json data to write
    :param object_name: S3 object name. If not specified then file_name is used
    :return: True if file was uploaded, else False
    """

    # If S3 object_name was not specified, use file_name
    if object_name is None:
        object_name = file_name

    # Upload the file
    s3 = boto3.resource('s3')
    try:
        s3object = s3.Object(bucket, file_name)
        response = s3object.put(Body=(bytes(json.dumps(json_data, indent=4, ensure_ascii=False).encode('utf-8'))))
    except ClientError as e:
        logging.error(e)
        return False
    return True

def harvest_uuids(uuid_list, gn_json_record_url_start, gn_json_record_url_end, bucket, bucket_location):
    """ Harvests GeoNetwork JSON file into s3_bucket_name
    
    :param uuid_list: list of uuids to upload
    :param gn_json_record_url: starting base path to the geonetwork record api
    :param gn_json_record_url: ending base path to the geonetwork record api
    :param bucket: bucket to upload to
    :return: accumulated error messages
    """
    
    error_msg = None
    
    if create_bucket(bucket, bucket_location):
        count = 0
        for uuid in uuid_list:
            try:
                """urllib
                req = urllib.request.Request(gn_json_record_url_start + uuid + gn_json_record_url_end)
                req.add_header('Accept', 'application/json; charset=utf-8')
                str_data = urllib.request.urlopen(req).read()
                """
                
                #requests
                headers = {
                    "Content-Type": "text/html; charset=utf-8",
                    "Accept": "application/json; charset=utf-8"
                }
                
                response = requests.get(gn_json_record_url_start + uuid + gn_json_record_url_end, headers=headers)
                str_data = json.loads(response.text)
                
                uuid_filename = uuid + ".json"
                #print(gn_json_record_url_start + uuid + gn_json_record_url_end)
                if upload_json_stream(uuid_filename, bucket, str_data):
                    count += 1
            except ClientError as e:
                logging.error(e)
                error_msg += e
        print("Uploaded", count, " records")
    else:
        error_msg = "Could not create S3 bucket: " + bucket

    return error_msg
    
    
""" def get_full_uuids_list(gn_q_query):
    #NOTE: function cannot finish in 15 minutes
    # Get a full list of all uuids
    #:param gn_q_query: URL of the GeoNetwork 'q' search
    #See https://geonetwork-opensource.org/manuals/3.10.x/en/api/q-search.html
    #:return: a full list of uuids to harvest
    
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
        print("Could not load the GeoNetwork 3.6 'q' search.")
        print("Cannot complete a full load of the dataset")
        print("Could not access: ", gn_q_query)
        return uuid_list
"""

def delete_uuids(uuid_deleted_list, bucket):
    """ Delete the json files in uuid_deleted_list from a s3 bucket
    Return a message to the user: delete xx uuid from xx bucket 

    :parm uuid_deleted_list: a list of uuid needs to be deleted 
    :parm bucket:bucket to delete from 

    """
    error_msg = None 
    count = 0 
    for uuid in uuid_deleted_list:    
        try: 
            uuid_filename = uuid + ".json"
            if delete_json_streams(uuid_filename, bucket):
                count += 1
        except ClientError as e: 
            logging.error(e)
            error_msg += e
    print('Deleted', count, " records")
        
    return error_msg

def delete_json_streams(filename, bucket): 
    """Delete a json file to an S3 bucket

    :param file_name: File to upload
    :param bucket: Bucket to upload to
    :return: True if file was deleted, else False
    """

    s3 = boto3.resource('s3')
    try: 
        s3object = s3.Object(bucket, filename)
        response = s3object.delete()
    except ClientError as e: 
        logging.error(e)
        return False
    return True 

