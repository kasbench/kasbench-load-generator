
The KASBench Load Generator is a FastAPI/Python application that uses Locust to generate a variable load on the GlobeCo application running in Kubernetes.  For each KASBench run, five instances of the KASBench Load Generator will be launched, each in its own Docker container.  Each instance will run a distinct load profile: _portfolio-manager_, _trader_, _back-office_, _investor_, or _it-operations_.  Each instance will make API calls to the GlobeCo application, which is running on Kubernetes.  Each KASBench Load Generator instance tracks its processing in a dedicated SQLite database.  The KASBench load generator is a FastAPI application that exposes a health API. 


## General Requirements

- The API will be exposed on port 8080
- This microservice will be written in Python using FastAPI
- This microservice will normally run in a Docker container.
- When launched, the microservice will expose an API as described below.
- The purpose of the service is to run Locust as a subprocess.  This service contains the code to expose the API and the Locust code to generate load.
- Locust is run as a subprocess.  It is kicked off by the POST /start API
- Only one subprocess can run at a time.  


## API

The KASBench Load Generator must support the following APIs.  No security is required.

### GET /health
	Response: {
	      "Status": "not-started", "running", or "completed"
	       "Role": "portfolio-manager", "trader", "back-office", "investor", or "it-operations"
		   "Health": "health" or "unhealthy",
		   "SuccessCount": 0,
		   "FailureCount": 0,
		   "InternalErrorCount": 0,
		   "LastFiveErrorMessages": ["msg 1", "msg 2", "msg 3", "msg 4", "msg 5"]	
		   "CurrentTimeStamp": "2026-06-01T10:18:00.000Z"
	}

HTTP Status Code: 200 - ok.  Anything else is treated as a failure

### POST /start

	Request object:      { 
			"Role": "portfolio-manager", "trader", "back-office", "investor", or "it-operations",
		    "BenchmarkLengthMinutes": 360,
		    "BaseLoadIntensity": 100,
		    "SpawnRate": 5,
		    "BaseDelayPercentage": 100,
			"KasbenchUrl": "http://servername:8080"
		}

	Response: {
			"StartTimeStamp": "2026-06-01T10:18:00.000Z"
	}

HTTP Status Code:  200 - ok, 400  409 - conflict (already running), 500 for non-recoverable errors, 503 for temporary errors

If a subprocess is already running, return a 409.

When this API is called, it runs Locust as a subprocess. The request object variables are passed to Locust as custom command line arguments (role, benchmark_length_minutes, base_load_intensity, spawn_rate, base_delay_percentage, and kasbench_url).

### POST /abort

	Request object:      { 
			
		}

	Response: {
			"StopTimeStamp": "2026-06-01T10:18:00.000Z"
	} 

HTTP Status Code: 200 - ok, 409 - conflict (not running), 500 for non-recoverable errors, 503 for temporary errors


### GET /download-db

Returns the SQLite database (media_type="application/x-sqlite3") as a streaming download.  It returns an error if the subprocess is running or the database is not available.

### GET/download-output

Returns the standard output (stdout and stderr) as a streaming text download.  It returns an error if the subprocess is running or the output is not available.


## Variable Load Intensity Shape

The benchmark runs for up to 1440 minutes.  Load intensities for the portfolio-manager, trader, back-office, and investor roles have been precalculated.  

When the POST `/start` API is called, it is passed the following settings in the request object:

- Role (Python: `role`): The role activated for this instance
- Ratio (Python: `ratio`): Compression ratio of the test.  Calculated as 1440/BenchmarkLengthMinutes.  The test will always simulate 24 hours.
- BaseLoadIntensity (Python: `base_load_intensity`): The baseline load intensity in percentage.  This can be used to dial up or down the user intensity for smaller or larger environments.
- SpawnRate (Python: `spawn_rate`): User increase per second

The variables above must be passed as custom command-line arguments to the Locust `environment` when it is started so that they are accessible to the custom shape class.  The following code provides a possible approach to how the custom shape could be implemented.  However, the INTENSITY_LOOKUP values are important and should be used.  These are the real values.

```python
import random
from locust import LoadTestShape

class KasbenchCustomShape(LoadTestShape):
    INTENSITY_LOOKUP = {
        "portfolio-manager": {
            0: 11, 30: 16, 60: 46, 90: 46, 120: 46, 150: 46, 
            180: 36, 210: 31, 240: 26, 270: 16, 300: 16, 330: 16, 
            360: 23, 390: 35, 420: 110, 450: 110, 480: 110, 510: 110, 
            540: 110, 570: 85, 600: 73, 630: 60, 660: 68, 690: 55, 
            720: 55, 750: 45, 780: 35, 810: 28, 840: 28, 870: 28, 
            900: 28, 930: 28, 960: 78, 990: 78, 1020: 78, 1050: 53, 
            1080: 28, 1110: 9, 1140: 9, 1170: 9, 1200: 9, 1230: 9, 
            1260: 9, 1290: 9, 1320: 9, 1350: 9, 1380: 9, 1410: 9
        },
        "trader": {
            0: 32, 30: 32, 60: 32, 90: 32, 120: 32, 150: 32, 
            180: 36, 210: 36, 240: 36, 270: 36, 300: 36, 330: 36, 
            360: 36, 390: 36, 420: 36, 450: 36, 480: 36, 510: 36, 
            540: 36, 570: 108, 600: 108, 630: 108, 660: 108, 690: 108, 
            720: 80, 750: 80, 780: 72, 810: 72, 840: 72, 870: 72, 
            900: 72, 930: 72, 960: 16, 990: 16, 1020: 8, 1050: 8, 
            1080: 12, 1110: 12, 1140: 12, 1170: 12, 1200: 12, 1230: 44, 
            1260: 44, 1290: 44, 1320: 44, 1350: 44, 1380: 44, 1410: 44
        },
        "back-office": {
            0: 36, 30: 36, 60: 36, 90: 36, 120: 36, 150: 36, 
            180: 36, 210: 36, 240: 36, 270: 36, 300: 36, 330: 36, 
            360: 36, 390: 36, 420: 166, 450: 166, 480: 166, 510: 166, 
            540: 166, 570: 166, 600: 166, 630: 166, 660: 166, 690: 166, 
            720: 166, 750: 166, 780: 166, 810: 166, 840: 166, 870: 130, 
            900: 130, 930: 130, 960: 130, 990: 130, 1020: 130, 1050: 130, 
            1080: 130, 1110: 130, 1140: 36, 1170: 36, 1200: 36, 1230: 36, 
            1260: 36, 1290: 36, 1320: 36, 1350: 36, 1380: 36, 1410: 36
        },
        "investor": {
            0: 26, 30: 26, 60: 26, 90: 26, 120: 26, 150: 26, 
            180: 26, 210: 26, 240: 26, 270: 26, 300: 26, 330: 26, 
            360: 26, 390: 26, 420: 26, 450: 26, 480: 44, 510: 44, 
            540: 44, 570: 44, 600: 44, 630: 44, 660: 44, 690: 44, 
            720: 44, 750: 44, 780: 44, 810: 44, 840: 44, 870: 44, 
            900: 44, 930: 44, 960: 44, 990: 44, 1020: 44, 1050: 44, 
            1080: 64, 1110: 64, 1140: 64, 1170: 64, 1200: 64, 1230: 64, 
            1260: 64, 1290: 64, 1320: 64, 1350: 64, 1380: 26, 1410: 26
        }
    }

    MAX_USERS = {
        "portfolio-manager": 175,
        "trader": 160,
        "back-office": 290,
        "investor": 100_000
    }
 
    RUN_MINUTES = 1440    
    EXOGENOUS_EVENT_MINUTE = random.randint(60, RUN_MINUTES - 60)
        

    def tick(self):
        env = self.environment
        
        # Actual run minutes
        actual_run_minutes = self.get_run_time() // 60
        # Simulated run minutes
        simulated_run_minutes  =  (self.get_run_time() * env.ratio) // 60
        
        if simulated_run_minutes >= self.RUN_MINUTES:
            return None

        if env.role == "it-operations":
            return (1, env.spawn_rate)
        
        # Step down to the nearest 30-second interval
        lookup_time = int((simulated_run_minutes // 30) * 30)
        
        # Fetch base intensity and scale by the custom load intensity percentage
        user_count = self.INTENSITY_LOOKUP[env.role][lookup_time]
        
        # Apply special processing for exogenous events
        if self.EXOGENOUS_EVENT_MINUTE - 30 <= simulated_run_minutes <= self.EXOGENOUS_EVENT_MINUTE + 30:
            user_count = max(int(1.5 * user_count), MAX_USERS[env.role])

        # Adjust for base load intensity
        user_count = user_count * (env.base_load_intensity / 100)
        
        return (user_count, env.spawn_rate)


```

## Tasks

Each of the five roles is expressed as an HTTP user.  When Locust is kicked off via an API call, it will run as a subprocess for one of the five roles.  Please generate a shell for the five user classes.  Please create a single task in each that sleeps for a minute.  The details of each role will be in a subsequent requirement.

The design of the SQLite database will be provided in a separate document.  For now, just create an empty database.




