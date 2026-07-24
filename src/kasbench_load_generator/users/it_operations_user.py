"""IT Operations role Locust user class."""
import random
import time

from locust import HttpUser, task, between

def generate_random_event_time_in_seconds(benchmark_length_minutes, lower_margin_percent=20, 
        upper_margin_percent=20):
    """Generates a random time in seconds between the lower margin percent and the upper margin percent"""    
    total_seconds = benchmark_length_minutes * 60
    start = total_seconds * lower_margin_percentage / 100.0 
    end = total_seconds - (total_seconds * upper_margin_percent / 100.0)
    return random.randint(start, end)


def upgrade_image(deployment_name, release_suffix="-high-cpu", namespace="globeco"):
    """ Upgrades and rolls out an image to a new release."""
    # Get the specified deployment using kr8s
    deploy = Deployment.get(deployment_name, namespace=namespace)
    # Get the image name from the first container
    image_name = deploy.spec.containers[0].image
    # Split the image name and tag
    image, tag = image_name.split(":")
    # Create the new image name with the release suffix
    new_image_name = f"{image}{release_suffix}:{tag}"
    # Update the deployment with the new image
    deploy.spec.containers[0].image = new_image_name
    # Apply the changes
    deploy.apply()

def run_batch(client):
    url = "/allocations/api/v1/executions/send"
    response = client.post(url)
    return response


class ItOperationsUser(HttpUser):
    """Simulates IT operations HTTP traffic."""

    wait_time = between(5, 5)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.benchmark_length_minutes = 5
        self.batch_job_start_time_in_seconds = 0
        self.cd_realease_time_in_seconds = 0
        self.batch_job_started = False
        self.cd_release_deployed = False

    def on_start(self):
        super().on_start()

        options = self.runner.environment.parsed_options
        self.benchmark_length_minutes: int = options.benchmark_length_minutes
        self.batch_job_start_time_in_seconds = generate_random_event_time_in_seconds(
            self.benchmark_length_minutes, lower_margin_percent=50, upper_margin_percent=80)
        print(
            f"Batch job will start at {self.batch_job_start_time_in_seconds} seconds into the benchmark"
        )

        self.cd_realease_time_in_seconds = generate_random_event_time_in_seconds(
            self.benchmark_length_minutes, lower_margin_percent=20, upper_margin_percent=30)
        print(
            f"CD release will start at {self.cd_realease_time_in_seconds} seconds into the benchmark"
        )


    @task
    def default_task(self) -> None:
         # Calculate the run time in seconds
        run_time = time.time() - self.environment.runner.state.start_time
        print(f"Current run time: {run_time:.2f} seconds")
        
        if not self.batch_job_started and run_time >= self.batch_job_start_time_in_seconds:
            # Run the batch job
            print("Batch job started!")
            response = run_batch(self.client) 
            if response.ok:
                print("Batch job completed successfully!")
                self.batch_job_started = True   
            else:
                print(f"Batch job failed with status code {response.status_code}")
                print(response.text)

        if not self.cd_release_deployed and run_time >= self.cd_realease_time_in_seconds:
            # Deploy the CD release
            upgrade_image("my-app-deployment")
            self.cd_release_deployed = True
            print("CD release deployed!")



