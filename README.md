# MP4Tuber
App that plays videos triggered by microphone input to simluate a vtuber/pngtuber like experience (mp4tuber).

This app has only been tested in windows 11

## install dependencies
You first need to install the libraries to use this application:

python.exe -m pip install -r dependencies.txt


# how to use this application
## Basic videos
You need to add a collection of mp4s in directories "Idle" and "Talking". The more videos you add to each directory, the better the effect will look as it will result in less repetition.

I recommend the talking videos to be kept short so when the character in the video is talking, it matches more accurate your voice. Longer videos have higher chance of not appearing in sync with your voice IRL.

## Launch the program:

python.exe video_tuber.py

## Saving and Loading settings
You can save the program settings on the drop down menu at the top left. Save/Load will create a file where you run the application. If you wish to backup your settings to a specific directory, use the backup options.

## Video player

### Start the video player
Press the "Start" button on the "Video" tab. You can stop the player by pressing "Stop" or press ESC on your keyboard with the video player window selected. 

### Available settings

#### Window
You can configure the size of the window that will be reproducing the videos along with a name for the window.

#### Microphone
You can select which microphone to use as an input. You need to press the refresh button to fetch the list of available microphones in your system.

To test the microphone input, press on "enable microphone test". This will show the microphone activty. Take note of the average volume value to use for the next fields. Talk for a couple of seconds and take note of the value. Keep silent for a couple of seconds and keep note of this value. You can use these values in the "Tresh" fields described next. You can then disable the test by pushing on the same button as before.

You can set the level at where to trigger the talking videos with the "Noise Tresh" parameter. The "Noise Dur" parameter (in seconds) is meant to try to avoid talking videos getting triggered by random noise. However, this setting cannot be set too high as it will delay a lot the start of the talking videos.

You can also set the silence level to set the videos back to idle using the "Slience Tresh" parameter. Likewise you can choose how long you want the silence to last before playing the idle state videos with the "Silence Dur" (in seconds). Adjust this setting accordingly depending on your talk speed. 


### Filters

The app comes with 4 default filters to make the video look like its being played on a CRT monitor. However, the most important filter is the "Glitch" filter. This is meant to ease the transition between videos. If you are replacing the filters, I highly recommend to add a filter that obscures part of the videos between transitions so the jump between videos is not that obvious ;3


# Advanced options

## MIDI

If you have a MIDI device such as a launchpad by novation, you can create a series of hotkeys to trigger specific videos such as emotes or loops.

### MIDI tab

Go to the mini tab and select the desired video you want to work with.

Create a new configuration file by pressing the "New" button.

Next, add a new entry to the configuration file by pressing "Add Button". After pressing the "Add button" go ahead and press the button on the MIDI device that you want to configure. The button will be added to the list and the light might come up on the device (only tested with launchpadS).

When you are satisfied with your changes, press the "Save Config" button. A red text indicator will tell you if you have unsaved changed.

### MIDI Reader

Once you have a configuration file selected, press the "Start MIDI Reader" button. This will start monitoring the MIDI device and when you press the buttons you configured, it will trigger emotes or loops. You need to have the video player running. You can see the MIDI reader state in the video tab too.

## MIDI button types

There are currently three types of buttons supported. Emotes, Loops, and Operations.

### Emotes
Emotes buttons will play a specific video only once in the "Emotes" directory. The name you type in the "Tag" field will be the name of the video loaded from the "Emotes" directory. I.E. if you set the tag of a button to "Sad", You should put the video for this emote in the directory "Emotes" and call it "Sad.mp4". 

If you want to cancel a video early, you can use the reset button from the video tab or you can configure one in your MIDI device from the "Operations" section.

### Loop
Loop buttons will play a specific video on a loop until the reset command is sent. You should first program a reset button before adding a loop button. You can see how to program a reset button in the "Operations" section. Alternatevly, you can use the "Reset" button in the "Video" tab.

Loop buttons will play a specific video in the "Loop" directory. The name you type in the "Tag" field will be the name of the video loaded from the "Loop" directory. I.E. if you set the tag of a button to "AFK", You should put the video for this emote in the directory "Loop" and call it "AFK.mp4". 


### Operations
Operations buttons are used to control the app. For now, the only option available is "Reset". 

"Reset" - Program a button to go back to the idle state. This is used to get out of the Loop videos. Select the button type as Operations and set the tag as "Reset".


