import time
import boto3
import requests
from botocore.exceptions import BotoCoreError, ClientError



def transcribe_file(job_name, file_uri, transcribe_client):
    transcribe_client.start_transcription_job(
        TranscriptionJobName = job_name,
        Media = {
            'MediaFileUri': file_uri
        },
        MediaFormat = 'mp3',
        LanguageCode = 'zh-CN'
    )
    
    try:
        max_tries = 60
        while max_tries > 0:
            max_tries -= 1
            job = transcribe_client.get_transcription_job(TranscriptionJobName = job_name)
            job_status = job['TranscriptionJob']['TranscriptionJobStatus']
            if job_status in ['COMPLETED', 'FAILED']:
                print(f"Job {job_name} is {job_status}.")
                if job_status == 'COMPLETED':
                    print(
                        f"Download the transcript from\n"
                        f"\t{job['TranscriptionJob']['Transcript']['TranscriptFileUri']}.")
                    try:
                        json_file = requests.get(job['TranscriptionJob']['Transcript']['TranscriptFileUri'])
                        open("./transcript.json", "wb").write(json_file.content)
                    except Exception as e:
                        print("Error occurred when downloading file, error message:")
                        print(e)
                break
            else:
                print(f"Waiting for {job_name}. Current status is {job_status}.")
            time.sleep(10)            
    except Exception as e:
        delete_job(job_name, transcribe_client)
    else:
        delete_job(job_name, transcribe_client)


def delete_job(job_name, transcribe_client):
    try:
        transcribe_client.delete_transcription_job(
            TranscriptionJobName=job_name)
        print("Delete job {}".format(job_name))
    except Exception as e:
        print(e)

def main():
    s3 = boto3.client("s3")
    speech_file = "speech.mp3"
    bucket = "vislabttsasr"
    s3.upload_file(Filename="./" + speech_file, Key=speech_file, Bucket=bucket)
    file_uri = "s3://{}/{}".format(bucket, speech_file)
    
    
    transcribe_client = boto3.client('transcribe')  
    transcribe_file('Transcribe', file_uri, transcribe_client)


if __name__ == '__main__':
    main()