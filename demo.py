import datetime
import time
import wave
import pyaudio
import keyboard
import requests
import os

import boto3
from boto3 import Session
from contextlib import closing


CHUNK = 1024
FORMAT = pyaudio.paInt16  # 16bit encoding wav
CHANNELS = 1  # single
RATE = 16000  # sample rate
MAX_RECORD_SECONDS = 1 * 60 # no longer than 1 minute 
MAX_LOOP_NUM = int(RATE / CHUNK * MAX_RECORD_SECONDS)

START = 0
END = 1



class Polly:
    def __init__(self) -> None:
        self.client = Session(profile_name="default").client("polly")

    def synthesize(self, input, file_name):
        text = ""           
        transcripts = input["transcripts"]
        for transcript in transcripts:
            text += transcript["transcript"]
        print('\"' + text + '\"')
        
        response = self.client.synthesize_speech(
            LanguageCode="cmn-CN", Text=text, OutputFormat="pcm", VoiceId="Zhiyu")
        
        if "AudioStream" in response:
            # Note: Closing the stream is important because the service throttles on the
            # number of parallel connections. Here we are using contextlib.closing to
            # ensure the close method of the stream object will be called automatically
            # at the end of the with statement's scope.                
                with closing(response["AudioStream"]) as pcm_stream:  
                    p = pyaudio.PyAudio()
                    stream = p.open(format=FORMAT,
                                    channels=CHANNELS,
                                    rate=RATE,
                                    output=True)

                    while True:
                        data = pcm_stream.read(CHUNK)
                        if not data:
                            break
                        stream.write(data)

                    stream.stop_stream()
                    stream.close()
                    p.terminate()                
        else:
            # The response didn't contain audio data, exit gracefully
            print("合成语音失败")
    
    

class Transcriber:
    def __init__(self) -> None:
        self.bucket = "vislabttsasr"
        self.client = boto3.client('transcribe')
        self.s3 = boto3.client("s3")
        self.job_name = "Transcribe"    
    
    def delete_job(self):
        try:
            self.client.delete_transcription_job(
                TranscriptionJobName=self.job_name)
            # print("Delete job {}".format(self.job_name))
        except Exception as e:
            print(e)
            
    
    def upload(self, file_name):
        file_path = os.path.join(os.getcwd(), "speech", file_name)
        self.s3.upload_file(Filename=file_path, Key=file_name, Bucket=self.bucket)
    
    def transcribe(self, file_name):
        self.upload(file_name)
        file_uri = "s3://{}/{}".format(self.bucket, file_name)
        
        self.delete_job()
        self.client.start_transcription_job(
            TranscriptionJobName = self.job_name,
            Media = {
                'MediaFileUri': file_uri
            },
            MediaFormat = 'wav',
            LanguageCode = 'zh-CN'
        )
        
        try:
            max_tries = 60
            while max_tries > 0:
                max_tries -= 1
                job = self.client.get_transcription_job(TranscriptionJobName = self.job_name)
                job_status = job['TranscriptionJob']['TranscriptionJobStatus']
                if job_status in ['COMPLETED', 'FAILED']:
                    # print(f"Job {self.job_name} is {job_status}.")
                    if job_status == 'COMPLETED':
                        # print(f"Download the transcript from\n")  
                            # f"\t{job['TranscriptionJob']['Transcript']['TranscriptFileUri']}.")
                        try:
                            response = requests.get(job['TranscriptionJob']['Transcript']['TranscriptFileUri'])
                            open(os.path.join(os.getcwd(), "transcript", file_name.split('.')[0]+'.json'), "wb").write(response.content)
                                                    
                        except Exception as e:
                            print("Error occurred when downloading file, error message:")
                            print(e)
                    else:
                        print("语音识别失败:(")
                    break
                else:
                    print("识别语音中...")
                    # print(f"Waiting for {self.job_name}. Current status is {job_status}.")
                time.sleep(5)  
                          
        except Exception as e:
            # self.delete_job()
            return {"results": None}
        else:
            # self.delete_job()
            return response.json()
        
        

class Recorder:
    def __init__(self) -> None:
       self.isRecording = False
       self.frames = []
       self.audio = None
       self.stream = None  
       self.transcriber = Transcriber()  
       self.tts = Polly()              
       
    def start_recording(self):
        self.isRecording = True
        self.audio = pyaudio.PyAudio()        
        self.stream = self.audio.open(format=FORMAT,
                    channels=CHANNELS,
                    rate=RATE,
                    input=True,
                    frames_per_buffer=CHUNK)
        print("录音【开始】，请您说话...\n")    
        i = 0
        while True:
            data = self.stream.read(CHUNK)
            self.frames.append(data)        
            i += 1
            if(keyboard.is_pressed("space") or i == MAX_LOOP_NUM):
                if(i == MAX_LOOP_NUM):
                    print("超过一分钟，自动结束录音")
                else:
                    beep(END)
                    print("--检测到您按下了空格键--")      
                self.stop_recording()
                break              
    
    def stop_recording(self):  
        self.isRecording = False
        file_name = datetime.datetime.now().strftime("%Y_%m_%d_%H%M%S.wav")
        
        try:
            self.stream.stop_stream()
            self.stream.close()
            self.audio.terminate() 
            print("录音【结束】，请稍候\n")     
            
            file_path = os.path.join(os.getcwd(), "speech", file_name)
            wf = wave.open(file_path, 'wb')
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(self.audio.get_sample_size(FORMAT))
            wf.setframerate(RATE)
            wf.writeframes(b''.join(self.frames))
            wf.close()
            # print(f"Saved to {file_path}") 
            
            result = self.transcriber.transcribe(file_name)["results"]
            
            if(result):
                self.tts.synthesize(result, file_name)
            else:
                print("无识别文本")
            
        except Exception as e:
            print(e)        
        self.frames = []
        


def beep(state):
    file_name = './audio/{}.wav'.format("start" if state == START else "end")    
    file = wave.open(file_name, 'rb')
    sample_rate = file.getframerate()
    num_channels = file.getnchannels()
    sample_width = file.getsampwidth()
    n_frames = file.getnframes()
    p = pyaudio.PyAudio()
    stream = p.open(format=p.get_format_from_width(sample_width),
                    channels=num_channels,
                    rate=sample_rate,
                    output=True)
    data = file.readframes(CHUNK)
    while data:
        stream.write(data)
        data = file.readframes(CHUNK)
    stream.stop_stream()
    stream.close()
    p.terminate()
    file.close()      


def keyboard_listener(recorder):
    print("请单击【空格键】开始说话，【Esc】退出：")
    while True:
        if keyboard.is_pressed('esc'):
            if recorder.isRecording:
                beep(END)     
                recorder.stop_recording()
            break
        if keyboard.is_pressed('space'):
            print("--检测到您按下了空格键--")
            beep(START)
            recorder.start_recording()
            time.sleep(1)
            print("\n请单击【空格键】开始说话，【Esc】退出：")
          

       
recorder = Recorder()
keyboard_listener(recorder)
