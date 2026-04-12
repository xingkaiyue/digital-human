import pyaudio


class MicRecorder:
    def __init__(self, rate=16000, channels=1, chunk=1024):
        self.rate = rate
        self.channels = channels
        self.chunk = chunk

        self.audio = pyaudio.PyAudio()
        self.stream = None

    def start(self):
        self.stream = self.audio.open(
            format=pyaudio.paInt16,
            channels=self.channels,
            rate=self.rate,
            input=True,
            frames_per_buffer=self.chunk
        )

    def read(self):
        return self.stream.read(self.chunk, exception_on_overflow=False)

    def stop(self):
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
        self.audio.terminate()