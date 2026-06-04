# Requirement 2: Create DockerFile

Create a DockerFile for this program

When I execute `docker run`, I want to be able to pass arguments for all of the following config settings:

| Constant | Value | Purpose |
|----------|-------|---------|
| `DB_PATH` | `/data/kasbench.db` | SQLite database written by Locust |
| `OUTPUT_PATH` | `/data/output.log` | Captured subprocess stdout/stderr |
| `HOST` | `0.0.0.0` | Server bind address |
| `PORT` | `8080` | Server port |
| `TERMINATION_TIMEOUT_SECONDS` | `10` | SIGTERM grace period before SIGKILL |
| `STATUS_UPDATE_TIMEOUT_SECONDS` | `5` | Max delay detecting subprocess exit |
| `RABBITMQ_HOST` | `localhost` | Hostname of RabbitMQ server |
| `RABBITMQ_PORT` | `5672` | Port of the RabbitMQ server |

Specifically, I want to be able to execute something like:

```bash
docker run -e DB_PATH=/home/ubuntu/data -e RABBITMQ_HOST=http://rabbitmq ...
```

I want to be able to override any of the above settings in this way.

Please create the docker file, a shell script to build the image and upload to Docker Hub, and update the README.md with examples of calling docker run.
