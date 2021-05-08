# HNAP JSON Harvesting Lambda

This AWS Lambda function harvests HNAP files in JSON format from the GeoNetwork v3.6 catalog and exports them into an S3 bucket.

## High-level description

Use an AWS cron to run every `10` minutes and overwrite any existing JSON files with the same UUID. Note: running every `10` minutes will overlap with 1). This is intentional and will capture an edge case where a Lambda cold start of a few milliseconds will not capture a full 10 minute window.

1) Default behaviour (no additional params in GET): use the GeoNetwork 'change' API to obtain a feed records that are new, modified, deleted or had their child/parent changed. This program will look backwards `11` minutes.

2) Special case: reload all JSON records
    `?runtype=full`

3) Special case: load all records since a specific dateTime using ISO 8601
    `?fromDateTime=yyyy-MM-ddTHH:mm:ssZ`

    E.g., `?fromDateTime=2021-04-29T00:00:00Z`

4) If GeoNetwork (https://maps.canada.ca/geonetwork) is inaccessible then exit.

Note: runtype and fromDateTime cannot be used together
