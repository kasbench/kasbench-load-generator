# Requirements Document

## Introduction

This feature adds Docker containerization to the kasbench-load-generator service. It includes a Dockerfile that packages the Python/uv application, exposes all configuration settings as environment variables with sensible defaults, provides a build-and-push shell script for Docker Hub publishing, and updates the README with docker run usage examples.

## Glossary

- **Dockerfile**: A text file containing instructions to assemble a Docker container image for the kasbench-load-generator service
- **Build_Script**: A shell script that builds the Docker image and pushes it to Docker Hub
- **Container**: A running instance of the kasbench-load-generator Docker image
- **Environment_Variable**: A key-value pair passed to the Container at runtime via `docker run -e`
- **Docker_Hub**: The public container registry where the built image is published
- **Load_Generator**: The kasbench-load-generator FastAPI microservice that manages Locust subprocesses

## Requirements

### Requirement 1: Dockerfile Creation

**User Story:** As a developer, I want a Dockerfile that builds the kasbench-load-generator into a container image, so that I can deploy the service in any Docker-compatible environment.

#### Acceptance Criteria

1. THE Dockerfile SHALL use a Python 3.12+ base image compatible with uv dependency management
2. THE Dockerfile SHALL install production dependencies only (excluding the dev dependency group) using `uv sync --no-dev` within the image build
3. THE Dockerfile SHALL copy pyproject.toml, uv.lock, main.py, and the src/ directory into the image
4. THE Dockerfile SHALL set the working directory to `/app`
5. THE Dockerfile SHALL set the default command to run the application entry point via `uv run python main.py`
6. THE Dockerfile SHALL expose port 8080 as the default service port
7. THE Dockerfile SHALL create the `/data` directory for database and output file storage

### Requirement 2: Environment Variable Configuration

**User Story:** As an operator, I want to override all configuration settings via environment variables at container runtime, so that I can customize behavior without rebuilding the image.

#### Acceptance Criteria

1. THE Container SHALL read DB_PATH from the corresponding Environment_Variable with a default value of `/data/kasbench.db`
2. THE Container SHALL read OUTPUT_PATH from the corresponding Environment_Variable with a default value of `/data/output.log`
3. THE Container SHALL read HOST from the corresponding Environment_Variable with a default value of `0.0.0.0`
4. THE Container SHALL read PORT from the corresponding Environment_Variable as an integer with a default value of `8080`
5. THE Container SHALL read TERMINATION_TIMEOUT_SECONDS from the corresponding Environment_Variable as an integer with a default value of `10`
6. THE Container SHALL read STATUS_UPDATE_TIMEOUT_SECONDS from the corresponding Environment_Variable as an integer with a default value of `5`
7. THE Container SHALL read RABBITMQ_HOST from the corresponding Environment_Variable with a default value of `localhost`
8. THE Container SHALL read RABBITMQ_PORT from the corresponding Environment_Variable as an integer with a default value of `5672`
9. WHEN an operator passes `-e KEY=VALUE` flags to `docker run`, THE Container SHALL use the provided values instead of the defaults
10. IF a numeric Environment_Variable (PORT, RABBITMQ_PORT, TERMINATION_TIMEOUT_SECONDS, STATUS_UPDATE_TIMEOUT_SECONDS) is set to a value that cannot be parsed as a positive integer, THEN THE Container SHALL fail to start and log an error message indicating which variable has an invalid value
11. THE Dockerfile SHALL declare each Environment_Variable using ENV instructions with the default values specified in criteria 1 through 8

### Requirement 3: Build and Push Script

**User Story:** As a developer, I want a shell script that builds the Docker image and pushes it to Docker Hub, so that I can publish new versions with a single command.

#### Acceptance Criteria

1. THE Build_Script SHALL build the Docker image using the Dockerfile in the project root
2. THE Build_Script SHALL accept a repository name as the first command-line argument and a version tag as the second command-line argument, using these to tag the built image as `<repository_name>:<version_tag>`
3. THE Build_Script SHALL push the tagged image to Docker_Hub
4. THE Build_Script SHALL be executable from the project root directory
5. IF the Docker build fails, THEN THE Build_Script SHALL exit with a non-zero status code and print an error message to stderr indicating the build failure
6. IF the Docker push fails, THEN THE Build_Script SHALL exit with a non-zero status code and print an error message to stderr indicating the push failure
7. IF the script is invoked without the required repository name or version tag arguments, THEN THE Build_Script SHALL exit with a non-zero status code and print a usage message to stderr indicating the expected arguments

### Requirement 4: README Documentation Update

**User Story:** As a developer, I want the README to include Docker usage examples, so that I can quickly understand how to run the service in a container.

#### Acceptance Criteria

1. THE README SHALL include a section containing a copy-paste-ready command to build the Docker image locally, specifying an image name placeholder (e.g., `kasbench-load-generator`)
2. THE README SHALL include a section containing a copy-paste-ready command to run the container with default settings, including the host-to-container port mapping for port 8080
3. THE README SHALL include a copy-paste-ready example of running the container with at least 2 environment variable overrides using the `-e` flag syntax
4. THE README SHALL list all 8 available environment variable names (DB_PATH, OUTPUT_PATH, HOST, PORT, TERMINATION_TIMEOUT_SECONDS, STATUS_UPDATE_TIMEOUT_SECONDS, RABBITMQ_HOST, RABBITMQ_PORT), their default values, and a one-line description of each variable's purpose in the Docker context
