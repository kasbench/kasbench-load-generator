# Requirements Document

## Introduction

This feature enhances the GET /health endpoint response for the KASBench Load Generator API. It adds timing fields (StartTime, EndTime), updates the StatusEnum to reflect more granular lifecycle states (success, failed, aborted), ensures all counters and error fields are properly updated during Locust execution, and introduces a POST /abort endpoint to terminate running subprocesses.

## Glossary

- **Load_Generator**: The KASBench Load Generator FastAPI application that manages Locust subprocess lifecycle
- **Health_Endpoint**: The GET /health API endpoint that returns the current state of the load generator
- **Abort_Endpoint**: The POST /abort API endpoint that terminates a running Locust subprocess
- **Subprocess_Manager**: The internal component that manages Locust process lifecycle, state, and counters
- **Locust_Process**: The Locust load testing subprocess spawned by the Load Generator
- **StatusEnum**: The enumeration defining valid subprocess lifecycle states: not-started, running, success, failed, aborted
- **HealthResponse**: The JSON response model returned by the Health Endpoint
- **StartTime**: An ISO 8601 UTC timestamp indicating when the POST /start request was processed
- **EndTime**: An ISO 8601 UTC timestamp indicating when the Locust Process completed execution, or null if still running
- **SuccessCount**: The count of successful Locust task executions reported by the Locust Process
- **FailureCount**: The count of failed Locust task executions reported by the Locust Process
- **InternalErrorCount**: The count of internal errors encountered by the Subprocess Manager
- **LastFiveErrorMessages**: A list of the five most recent internal error messages maintained by the Subprocess Manager

## Requirements

### Requirement 1: StartTime Field in Health Response

**User Story:** As an operator, I want to see when the load test started, so that I can track test duration and correlate results with other system events.

#### Acceptance Criteria

1. WHEN the Health_Endpoint is called after a POST /start request has returned an HTTP 200 response, THE Health_Endpoint SHALL return a StartTime field containing the UTC timestamp of when the POST /start request was processed, formatted as `YYYY-MM-DDTHH:MM:SS.mmmZ` with millisecond precision
2. WHEN the Health_Endpoint is called before any POST /start request has been made, THE Health_Endpoint SHALL return a StartTime field with a JSON null value
3. WHEN a new POST /start request is processed and returns an HTTP 200 response, THE Subprocess_Manager SHALL record the current UTC timestamp as the StartTime, replacing any previously stored StartTime value
4. WHILE the subprocess status is "success", "failed", or "aborted", THE Health_Endpoint SHALL continue to return the StartTime value that was recorded when the most recent POST /start request was processed

### Requirement 2: EndTime Field in Health Response

**User Story:** As an operator, I want to see when the load test ended, so that I can determine total execution duration and know if a test is still in progress.

#### Acceptance Criteria

1. WHILE the Locust_Process is running, THE Health_Endpoint SHALL return an EndTime field with a JSON null value in the response body
2. WHEN the Locust_Process terminates on its own (process exits without an abort request), THE Subprocess_Manager SHALL record the current UTC timestamp as the EndTime in ISO 8601 format with millisecond precision (YYYY-MM-DDThh:mm:ss.mmmZ)
3. WHEN the Locust_Process is aborted via the Abort_Endpoint, THE Subprocess_Manager SHALL record the current UTC timestamp as the EndTime in ISO 8601 format with millisecond precision (YYYY-MM-DDThh:mm:ss.mmmZ)
4. WHEN the Health_Endpoint is called before any POST /start request has been made, THE Health_Endpoint SHALL return an EndTime field with a JSON null value
5. WHEN a new POST /start request is processed, THE Subprocess_Manager SHALL reset the EndTime to null so that subsequent GET /health responses return a JSON null EndTime until the process terminates or is aborted

### Requirement 3: Updated StatusEnum Values

**User Story:** As an operator, I want more granular status information, so that I can distinguish between successful completions, failures, and deliberate aborts.

#### Acceptance Criteria

1. THE StatusEnum SHALL define exactly five values: "not-started", "running", "success", "failed", "aborted"
2. WHEN the Locust_Process exits with a zero exit code and was not terminated via the Abort_Endpoint, THE Subprocess_Manager SHALL set the status to "success"
3. WHEN the Locust_Process exits with a non-zero exit code and was not terminated via the Abort_Endpoint, THE Subprocess_Manager SHALL set the status to "failed"
4. WHEN the Locust_Process is terminated via the Abort_Endpoint, THE Subprocess_Manager SHALL set the status to "aborted" after the process has exited, regardless of the exit code
5. WHEN a new POST /start request passes validation and the Locust subprocess is successfully spawned, THE Subprocess_Manager SHALL set the status to "running"
6. THE Load_Generator SHALL initialize with status set to "not-started"
7. IF a POST /start request fails due to a system error during subprocess launch, THEN THE Subprocess_Manager SHALL leave the status unchanged from its value prior to the request

### Requirement 4: Correct Counter Updates During Execution

**User Story:** As an operator, I want accurate success and failure counts, so that I can assess load test outcomes without downloading the full results database.

#### Acceptance Criteria

1. WHILE the Locust_Process is running, THE Subprocess_Manager SHALL read the Locust statistics database every 1 second to update SuccessCount with the total number of successful requests
2. WHILE the Locust_Process is running, THE Subprocess_Manager SHALL read the Locust statistics database every 1 second to update FailureCount with the total number of failed requests
3. WHEN the Subprocess_Manager encounters an error while reading the Locust statistics database or updating counters, THE Subprocess_Manager SHALL increment InternalErrorCount by one
4. WHEN the Subprocess_Manager encounters an error while reading the Locust statistics database or updating counters, THE Subprocess_Manager SHALL append the error message to LastFiveErrorMessages
5. THE Subprocess_Manager SHALL retain only the five most recent error messages in LastFiveErrorMessages in chronological order (oldest first), evicting the oldest entry when a sixth is added
6. WHEN a new POST /start request is processed, THE Subprocess_Manager SHALL reset SuccessCount to 0, FailureCount to 0, InternalErrorCount to 0, and LastFiveErrorMessages to an empty list before launching the Locust_Process
7. WHEN the Locust_Process terminates naturally, THE Subprocess_Manager SHALL perform one final read of the Locust statistics database to ensure SuccessCount and FailureCount reflect the final totals before ceasing monitoring

### Requirement 5: POST /abort Endpoint

**User Story:** As an operator, I want to abort a running load test, so that I can stop tests that are no longer needed or are causing problems.

#### Acceptance Criteria

1. WHILE the Subprocess_Manager status is "running", WHEN the Abort_Endpoint receives a POST request, THE Abort_Endpoint SHALL send SIGTERM to the Locust_Process and wait up to 10 seconds for the process to exit
2. IF the Locust_Process does not exit within 10 seconds after SIGTERM, THEN THE Abort_Endpoint SHALL send SIGKILL to force-terminate the Locust_Process
3. WHEN the Abort_Endpoint successfully terminates the Locust_Process, THE Abort_Endpoint SHALL return HTTP 200 with a JSON body containing a single field "StopTimeStamp" in ISO 8601 UTC format with millisecond precision (YYYY-MM-DDThh:mm:ss.mmmZ)
4. WHEN the Abort_Endpoint successfully terminates the Locust_Process, THE Subprocess_Manager SHALL set the status to "aborted" and record the EndTime as the current UTC timestamp in ISO 8601 format with millisecond precision
5. WHEN the Abort_Endpoint receives a POST request while the Subprocess_Manager status is "not-started", "success", "failed", or "aborted", THE Abort_Endpoint SHALL return HTTP 409 with a JSON body containing an "error" field with a message indicating no subprocess is running
6. IF an operating system error occurs during termination (e.g., process already exited, permission denied), THEN THE Abort_Endpoint SHALL return HTTP 500 with a JSON body containing an "error" field with a message describing the failure
7. IF an operating system error occurs during termination, THEN THE Subprocess_Manager SHALL set the status to "failed" and record the error in the internal error list
