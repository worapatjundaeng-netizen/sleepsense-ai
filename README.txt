# Audio-Polygraphy Dataset for Sleep Apnea Analysis (APSAA)

The Audio-Polygraphy Dataset for Sleep Apnea Analysis (APSAA) provides synchronized, full-night  
audio and polygraph recordings from 32 subjects, accompanied by manual annotations of labeled  
events in the polygraph studies. All participants received detailed information about the study,  
and written informed consent was obtained from those who agreed to participate. The recordings  
were collected between September 2021 and April 2022 at the Sleep Unit of Dr. Sagaz Hospital in  
Jaén (Spain). The study was approved by the Provincial Research Ethics Committee of Jaén (Spain).  

## Dataset Organization  

Each subject's data is stored in a folder named according to their unique identification code.  
Within each folder, users will find:  

1. The audio recording in WAV format.  
2. Separate CSV files for each polygraph signal.  
3. A CSV file containing manual annotations of polygraph events.  

## Polygraph Signals  

The dataset includes the following polygraph signals:  

- **Abdomen_EG**: Abdominal respiratory effort.  
- **Flow_EG**: Nasal airflow from the nasal cannula.  
- **Pulse_EG**: Pulse rate, measured in beats per minute.  
- **Snore_EG**: Respiratory snore pressure envelope from the nasal cannula.  
- **SpO2_EG**: Peripheral oxygen saturation percentage.  
- **Thermistor_EG**: Oronasal thermal airflow.  
- **Thorax_EG**: Thoracic respiratory effort.  

The sampling rate for each signal is specified in the file `Polygraph_Sampling_Rates.csv`.  

## Manual Annotations  

The annotation files include three columns:  

- **Event_Name**: Name of the polygraph event. The different values and their corresponding  
  polygraph signals are:  

  --------------------------------------------------------------------  
  | Event Name                                 | Polygraph Signal    |  
  --------------------------------------------------------------------  
  | Snore                                      | Snore Pressure      |  
  | Obstructive Apnea / Central Apnea          | Nasal Flow          |  
  | Mixed Apnea / Hypopnea                     | Nasal Flow          |  
  | No Effort                                  | Thorax / Abdomen    |  
  | Desaturation                               | SpO2                |  
  --------------------------------------------------------------------  

- **Start_Time**: Initial time of the event, formatted as hh:mm:ss.  
- **Duration**: Duration of the event, in seconds.  

## Synchronization Algorithm  

An automated algorithm for synchronizing audio and polygraph signals in sleep studies is provided  
with this dataset. The code can be accessed via the following GitHub repository:  

https://github.com/fdgonzal/Polygraph-Audio-Sync  
