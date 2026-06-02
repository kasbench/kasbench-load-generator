# Requirements Document

## Introduction

The KASBench Load Generator is a FastAPI/Python microservice that uses Locust to generate variable load against the GlobeCo application running in Kubernetes. Five instances run concurrently in separate Docker containers, each executing a distinct load profile (portfolio-manager, trader, back-office, investor, or it-operations). The service exposes a REST API for lifecycle management, health monitoring, and artifact retrieval. Each instance tracks its processing in a dedicated SQLite database.

## Glossary

- **Load_Generator**: The KASBench Load Generator FastAPI application that exposes the REST API and manages the Locust subprocess
- **Locust_Subprocess**: The Locust load testing process launched by the Load_Generator as a child process
- **Role**: One of five load profiles: portfolio-manager, trader, back-office, investor, or it-operations
- **GlobeCo_Application**: The target Kubernetes application that receives generated load
- **INTENSITY_LOOKUP**: A predefined dictionary mapping each Role to a table of simulated-minute-to-user-count values at 30-minute intervals over a 1440-minute simulated day
- **Custom_Shape**: A Locust LoadTestShape subclass that calculates user counts per tick using the INTENSITY_LOOKUP table, ratio, and base_load_intensity
- **Exogenous_Event**: A randomly placed 60-minute spike window where user counts increase to max(1.5× base, MAX_USERS) for the given Role
- **Ratio**: Compression factor calculated as 1440 divided by BenchmarkLengthMinutes, used to map actual elapsed time to simulated time
- **Base_Load_Intensity**: A percentage multiplier applied to INTENSITY_LOOKUP values to scale load up or down
- **Spawn_Rate**: The number of Locust users added per second when ramping up
- **SQLite_Database**: A per-instance SQLite database file used to track load generation processing
- **Health_Response**: The JSON object returned by the GET /health endpoint containing status, role, health, counters, errors, and timestamp

## Requirements

### Requirement 1: API Server Configuration

**User Story:** As a KASBench operator, I want the Load_Generator to expose its API on a predictable port, so that container orchestration can route traffic to it.

#### Acceptance Criteria

1. THE Load_Generator SHALL bind the FastAPI application to host 0.0.0.0 on port 8080, accepting connections from any network interface
2. THE Load_Generator SHALL accept HTTP requests without authentication or authorization on all exposed endpoints

### Requirement 2: Health Endpoint

**User Story:** As a KASBench orchestrator, I want to query the health of each Load_Generator instance, so that I can monitor benchmark progress and detect failures.

#### Acceptance Criteria

1. WHEN a GET request is received at /health, THE Load_Generator SHALL return an HTTP 200 response with a JSON body containing Status, Role, Health, SuccessCount, FailureCount, InternalErrorCount, LastFiveErrorMessages, and CurrentTimeStamp fields
2. IF no Locust subprocess has been launched since the Load_Generator started, THEN THE Load_Generator SHALL report Status as "not-started" and Role as an empty string
3. WHILE the Locust subprocess is executing, THE Load_Generator SHALL report Status as "running" and Role as the role value provided in the POST /start request
4. WHEN the Locust subprocess terminates, THE Load_Generator SHALL report Status as "completed"
5. IF InternalErrorCount is 0, THEN THE Load_Generator SHALL report Health as "healthy"
6. IF InternalErrorCount is greater than 0, THEN THE Load_Generator SHALL report Health as "unhealthy"
7. THE Load_Generator SHALL include the current UTC timestamp in ISO 8601 format (e.g., "2026-06-01T10:18:00.000Z") in the CurrentTimeStamp field
8. THE Load_Generator SHALL maintain LastFiveErrorMessages as a JSON array containing up to 5 entries, where each entry is the message from the most recent internal errors in chronological order, and SHALL return an empty array when no errors have occurred

### Requirement 3: Start Endpoint

**User Story:** As a KASBench orchestrator, I want to start a load generation run with specific parameters, so that I can control the intensity and duration of the benchmark.

#### Acceptance Criteria

1. WHEN a POST request is received at /start with a valid request body, THE Load_Generator SHALL launch the Locust_Subprocess and return an HTTP 200 response containing a StartTimeStamp in ISO 8601 format
2. WHEN a POST request is received at /start with a missing or invalid field, THE Load_Generator SHALL return an HTTP 400 response with an error message indicating which field failed validation and why
3. WHEN a POST request is received at /start while a Locust_Subprocess is already running, THE Load_Generator SHALL return an HTTP 409 response indicating a conflict
4. THE Load_Generator SHALL accept the following fields in the /start request body: Role (string), BenchmarkLengthMinutes (integer, minimum 1, maximum 1440), BaseLoadIntensity (integer, minimum 1, maximum 1000), SpawnRate (integer, minimum 1, maximum 100), BaseDelayPercentage (integer, minimum 0, maximum 1000), and KasbenchUrl (string, valid HTTP or HTTPS URL format)
5. THE Load_Generator SHALL validate that Role is one of: portfolio-manager, trader, back-office, investor, or it-operations
6. THE Load_Generator SHALL pass Role, BenchmarkLengthMinutes, BaseLoadIntensity, SpawnRate, BaseDelayPercentage, and KasbenchUrl to the Locust_Subprocess as custom command-line arguments
7. IF the Locust_Subprocess fails to start due to a system-level error such as the executable not being found or insufficient permissions, THEN THE Load_Generator SHALL return an HTTP 500 response with an error message indicating the failure reason
8. IF the Locust_Subprocess fails to start due to a resource constraint such as insufficient memory or too many open processes, THEN THE Load_Generator SHALL return an HTTP 503 response with an error message indicating the temporary unavailability

### Requirement 4: Abort Endpoint

**User Story:** As a KASBench orchestrator, I want to abort a running load generation, so that I can stop the benchmark early if needed.

#### Acceptance Criteria

1. WHILE a Locust_Subprocess is running, WHEN a POST request is received at /abort, THE Load_Generator SHALL terminate the Locust_Subprocess within 10 seconds, update the status to "completed", and return an HTTP 200 response containing a JSON body with a "StopTimeStamp" field in ISO 8601 format (e.g., "2026-06-01T10:18:00.000Z")
2. IF a POST request is received at /abort while no Locust_Subprocess is running, THEN THE Load_Generator SHALL return an HTTP 409 response with a JSON body containing an error message indicating that no subprocess is currently running
3. IF the Locust_Subprocess does not terminate within 10 seconds after a SIGTERM signal, THEN THE Load_Generator SHALL forcefully kill the subprocess and return an HTTP 200 response containing the "StopTimeStamp"
4. IF a non-recoverable error occurs during subprocess termination (e.g., the process cannot be found or the OS refuses the signal), THEN THE Load_Generator SHALL return an HTTP 500 response with a JSON body containing an error message indicating the failure reason
5. IF a temporary error occurs during subprocess termination (e.g., system resource exhaustion that may resolve on retry), THEN THE Load_Generator SHALL return an HTTP 503 response with a JSON body containing an error message indicating the temporary nature of the failure

### Requirement 5: Database Download Endpoint

**User Story:** As a KASBench orchestrator, I want to download the SQLite database after a run completes, so that I can analyze the load generation results.

#### Acceptance Criteria

1. WHEN a GET request is received at /download-db after the Locust_Subprocess has completed and the SQLite_Database file exists, THE Load_Generator SHALL return the SQLite_Database file as a streaming response with media type "application/x-sqlite3" and HTTP status 200
2. IF a GET request is received at /download-db while a Locust_Subprocess is running, THEN THE Load_Generator SHALL return an HTTP 409 response with a JSON body containing an error message indicating the subprocess is still active
3. IF a GET request is received at /download-db and no SQLite_Database file exists, THEN THE Load_Generator SHALL return an HTTP 404 response with a JSON body containing an error message indicating the database is not available

### Requirement 6: Output Download Endpoint

**User Story:** As a KASBench orchestrator, I want to download the subprocess output after a run completes, so that I can review Locust stdout and stderr for diagnostics.

#### Acceptance Criteria

1. WHEN a GET request is received at /download-output after the Locust_Subprocess has completed and output content has been captured, THE Load_Generator SHALL return the captured stdout followed by stderr as a streaming response with media_type "text/plain" and HTTP status 200
2. IF a GET request is received at /download-output while a Locust_Subprocess is running, THEN THE Load_Generator SHALL return an HTTP 409 response with a JSON body containing an error message indicating the subprocess is still active
3. IF a GET request is received at /download-output and no Locust_Subprocess has been started since the service launched, THEN THE Load_Generator SHALL return an HTTP 404 response with a JSON body containing an error message indicating no output is available
4. IF a GET request is received at /download-output after the Locust_Subprocess has completed but the captured output is empty (zero bytes of stdout and stderr), THEN THE Load_Generator SHALL return an HTTP 200 response with an empty text/plain streaming response

### Requirement 7: Single Subprocess Constraint

**User Story:** As a KASBench operator, I want the Load_Generator to enforce a single subprocess limit, so that resource contention does not corrupt benchmark results.

#### Acceptance Criteria

1. THE Load_Generator SHALL permit at most one Locust_Subprocess to execute at any given time
2. WHEN the Locust_Subprocess terminates (either naturally or via abort), THE Load_Generator SHALL update its internal status to "completed" within 5 seconds of process exit
3. WHEN a new /start request is received after a previous run has completed, THE Load_Generator SHALL launch a new Locust_Subprocess, reset SuccessCount, FailureCount, InternalErrorCount, and LastFiveErrorMessages to their initial values, and update the status to "running"

### Requirement 8: Variable Load Intensity Shape

**User Story:** As a KASBench designer, I want load intensity to follow precalculated profiles, so that the benchmark simulates realistic usage patterns over a compressed 24-hour period.

#### Acceptance Criteria

1. THE Custom_Shape SHALL use the INTENSITY_LOOKUP table to determine user counts at 30-minute simulated intervals for the portfolio-manager, trader, back-office, and investor Roles, returning a tuple of (user_count, Spawn_Rate) from the tick method
2. THE Custom_Shape SHALL calculate simulated elapsed minutes as the integer floor of (actual elapsed seconds multiplied by Ratio) divided by 60
3. IF simulated elapsed minutes reaches or exceeds 1440, THEN THE Custom_Shape SHALL terminate the load test by returning None from the tick method
4. WHEN the Role is it-operations, THE Custom_Shape SHALL return a constant user count of 1 with the configured Spawn_Rate, bypassing INTENSITY_LOOKUP
5. THE Custom_Shape SHALL compute the final user count as the integer floor of the INTENSITY_LOOKUP value multiplied by Base_Load_Intensity divided by 100
6. THE Custom_Shape SHALL compute the lookup key by flooring simulated elapsed minutes to the nearest lower 30-minute boundary (i.e., integer division by 30, multiplied by 30) for INTENSITY_LOOKUP access
7. THE Custom_Shape SHALL select a random exogenous event minute between 60 and 1380 (inclusive) once at class load time, and WHILE simulated elapsed minutes is within 30 minutes before or after that event minute, THE Custom_Shape SHALL set user_count to the greater of 1.5 times the INTENSITY_LOOKUP value or the role's MAX_USERS cap before applying Base_Load_Intensity scaling

### Requirement 9: Exogenous Event Simulation

**User Story:** As a KASBench designer, I want a random load spike during the benchmark, so that the system under test is stressed by unpredictable surges.

#### Acceptance Criteria

1. THE Custom_Shape SHALL select a uniformly random Exogenous_Event minute between 60 and 1380 (inclusive) once at class-level initialization, so that the value remains constant for the entire benchmark run
2. WHEN the simulated elapsed minutes falls within the range [Exogenous_Event minute − 30, Exogenous_Event minute + 30] (inclusive) and the current Role is not it-operations, THE Custom_Shape SHALL replace the INTENSITY_LOOKUP user count with the greater of the integer value of 1.5 times the INTENSITY_LOOKUP user count and the MAX_USERS value for the current Role, before base_load_intensity scaling is applied
3. THE Custom_Shape SHALL define MAX_USERS as: portfolio-manager=175, trader=160, back-office=290, investor=100000

### Requirement 10: Locust User Classes

**User Story:** As a KASBench developer, I want each Role to have a dedicated Locust HttpUser class, so that role-specific behavior can be implemented independently.

#### Acceptance Criteria

1. THE Load_Generator SHALL define five Locust HttpUser subclasses: PortfolioManagerUser, TraderUser, BackOfficeUser, InvestorUser, and ItOperationsUser
2. Each Locust HttpUser subclass SHALL contain a single task decorated with @task that sleeps for 60 seconds using the Locust between() wait mechanism or equivalent
3. THE Load_Generator SHALL launch the Locust_Subprocess with only the HttpUser subclass corresponding to the Role specified in the /start request

### Requirement 11: SQLite Database Initialization

**User Story:** As a KASBench developer, I want an empty SQLite database created for each run, so that load generation results can be tracked.

#### Acceptance Criteria

1. WHEN the Locust_Subprocess is launched, THE Load_Generator SHALL delete any previously existing SQLite_Database file at the target path and create a new valid empty SQLite database file (containing no application tables) before the Locust process begins execution
2. THE Load_Generator SHALL store the SQLite_Database file at a fixed filesystem path within the container that is used by both the FastAPI application and the GET /download-db endpoint to read the file
3. IF the Load_Generator fails to create the SQLite_Database file, THEN THE Load_Generator SHALL return a 500 HTTP status code in response to the POST /start request and SHALL NOT launch the Locust_Subprocess

### Requirement 12: Subprocess Output Capture

**User Story:** As a KASBench operator, I want stdout and stderr from the Locust subprocess captured, so that I can review diagnostic output after a run.

#### Acceptance Criteria

1. WHEN the Locust_Subprocess is launched, THE Load_Generator SHALL capture both stdout and stderr from the subprocess by redirecting them to a single output file
2. THE Load_Generator SHALL store the captured output file at a fixed filesystem path within the container that is used by the GET /download-output endpoint
3. THE Load_Generator SHALL interleave stdout and stderr output in the order received by the operating system, appending all content to the output file in real time
4. WHEN a new /start request is received after a previous run, THE Load_Generator SHALL delete the previous output file and begin capturing to a fresh file
