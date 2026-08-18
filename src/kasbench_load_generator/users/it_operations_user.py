"""IT Operations role Locust user class."""
import logging
import random
import time
import os
import yaml
import base64

import requests as raw_requests
from locust import HttpUser, task, between

logging.basicConfig(level=logging.INFO)


def extract_kubeconfig_and_dump_certs(config_path="~/.kube/config"):
    """Parses a self-managed k8s kubeconfig to extract certificates dynamically."""
    expanded_path = os.path.expanduser(config_path)
    
    if not os.path.exists(expanded_path):
        raise FileNotFoundError(f"Kubeconfig file not found at {expanded_path}")
        
    with open(expanded_path, "r") as f:
        config = yaml.safe_load(f)
        
    # 1. Resolve Active Context
    current_context_name = config.get("current-context")
    context_data = next(c["context"] for c in config["contexts"] if c["name"] == current_context_name)
    namespace = context_data.get("namespace", "globeco")
    
    # 2. Extract API Server Address
    cluster_name = context_data["cluster"]
    cluster_data = next(c["cluster"] for c in config["clusters"] if c["name"] == cluster_name)
    host = cluster_data["server"]
    
    # 3. Extract Active User Details
    user_name = context_data["user"]
    user_data = next(u["user"] for u in config["users"] if u["name"] == user_name)
    
    # Define local path where certs will be written temporarily on the EC2 instance
    cert_dir = os.path.expanduser("/tmp/locust_k8s_certs")
    os.makedirs(cert_dir, exist_ok=True)
    
    ca_file_path = os.path.join(cert_dir, "ca.crt")
    cert_file_path = os.path.join(cert_dir, "client.crt")
    key_file_path = os.path.join(cert_dir, "client.key")

    # 4. Extract and Base64 Decode CA Data
    if "certificate-authority-data" in cluster_data:
        ca_bytes = base64.b64decode(cluster_data["certificate-authority-data"])
        with open(ca_file_path, "wb") as f:
            f.write(ca_bytes)
    else:
        # If the file links to a local disk path instead of embedded data
        ca_file_path = cluster_data.get("certificate-authority", True)

    # 5. Extract and Base64 Decode Client Credentials
    if "client-certificate-data" in user_data and "client-key-data" in user_data:
        cert_bytes = base64.b64decode(user_data["client-certificate-data"])
        key_bytes = base64.b64decode(user_data["client-key-data"])
        
        with open(cert_file_path, "wb") as f:
            f.write(cert_bytes)
        with open(key_file_path, "wb") as f:
            f.write(key_bytes)
            
        cert_tuple = (cert_file_path, key_file_path)
    else:
        # Fallback to local files if path-based config is used
        cert_tuple = (user_data.get("client-certificate"), user_data.get("client-key"))

    return host, namespace, ca_file_path, cert_tuple

# Parse config ONCE at execution initialization
try:
    K8S_HOST, K8S_NAMESPACE, CA_PATH, CLIENT_CERT_TUPLE = extract_kubeconfig_and_dump_certs("~/.kube/config")
    logging.info(f"K8S_HOST={K8S_HOST}, CA_PATH={CA_PATH}, CLIENT_CERT_TUPLE={CLIENT_CERT_TUPLE}, K8S_NAMESPACE={K8S_NAMESPACE}")
except Exception as e:
    logging.info(f"Error parsing local kubeconfig: {e}")
    # Fallbacks to prevent crash before runtime loops
    K8S_HOST, K8S_NAMESPACE, CA_PATH, CLIENT_CERT_TUPLE = "https://127.0.0.1:6443", "default", True, None


def generate_random_event_time_in_seconds(benchmark_length_minutes, lower_margin_percent=20, 
        upper_margin_percent=20):
    """Generates a random time in seconds between the lower margin percent and the upper margin percent"""    
    total_seconds = benchmark_length_minutes * 60
    start = total_seconds * lower_margin_percent / 100.0 
    end = total_seconds - (total_seconds * upper_margin_percent / 100.0)
    return random.randint(int(start), int(end))



def run_batch(client):
    """Runs the allocations batch job."""
    url = "/allocations/api/v1/executions/send"
    response = client.post(url)
    return response

def get_current_image_name_and_tag(deployment_name, container_name=None):
    """Fetches the current image name and tag for a container in a deployment."""
    if not container_name:
        container_name = deployment_name
    
    url = f"{K8S_HOST}/apis/apps/v1/namespaces/{K8S_NAMESPACE}/deployments/{deployment_name}"

    response = raw_requests.get(
        url,
        verify=CA_PATH,
        cert=CLIENT_CERT_TUPLE,
        timeout=30,
    )

    if response.status_code != 200:
        logging.error(f"Failed to fetch deployment: Status {response.status_code}")
        logging.error(f"Response: {response.text}")
        raise ValueError(f"Error fetching deployment: {response.status_code}")

    deployment_data = response.json()
    
    # Target the containers array inside the pod template spec
    containers = deployment_data["spec"]["template"]["spec"]["containers"]
    
    # Find the matching container and extract its image name
    for container in containers:
        if container["name"] == container_name:
            current_image = container["image"]
            image_name, image_tag = current_image.split(":", 1)
            return image_name, image_tag
    
    raise ValueError(f"Container '{container_name}' not found in deployment '{deployment_name}'")


def patch_deployment(client, deployment_name, patch_payload, namespace="globeco"):
    """Patches a deployment with the given payload via raw requests."""
    url = f"{K8S_HOST}/apis/apps/v1/namespaces/{namespace}/deployments/{deployment_name}"
    logging.info(f"Sending PATCH request to {url}")
    response = raw_requests.patch(
        url,
        verify=CA_PATH,
        cert=CLIENT_CERT_TUPLE,
        json=patch_payload,
        headers={"Content-Type": "application/strategic-merge-patch+json"},
        timeout=30,
    )
    logging.info(f"PATCH response: {response.status_code} - {response.text}")
    return response


def upgrade_image(client, deployment_name, container_name=None, release_suffix="-high-cpu", namespace="globeco"):
    """Upgrades and rolls out an image to a new release."""
    if not container_name:
        container_name = deployment_name

    # Get the current image name and tag
    image, tag = get_current_image_name_and_tag(deployment_name, container_name)
    # Create the new image name with the release suffix
    new_image_name = f"{image}{release_suffix}:{tag}"
    logging.info(f"Upgrading deployment {deployment_name} to {new_image_name}")
    # Update the deployment with the new image via patch
    patch_payload = {
        "spec": {
            "template": {
                "spec": {
                    "containers": [
                        {
                            "name": container_name,
                            "image": new_image_name,
                        }
                    ]
                }
            }
        }
    }

    response = patch_deployment(client, deployment_name, patch_payload, namespace)
    if response.status_code == 200:
        logging.info(f"Successfully upgraded deployment {deployment_name} to {new_image_name}")
    else:
        logging.error(f"Failed to upgrade deployment {deployment_name}: {response.status_code}")
        logging.error(response.text)
        raise Exception(f"Failed to upgrade deployment {deployment_name}: {response.status_code}")
    return response


class ItOperationsUser(BaseUser):
    """Simulates IT operations HTTP traffic."""

    wait_time = between(5, 5)
    host = K8S_HOST

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.benchmark_length_minutes = 5
        self.batch_job_start_time_in_seconds = 0
        self.cd_release_time_in_seconds = 0
        self.batch_job_started = False
        self.cd_release_deployed = False
        self.deployment_name = "globeco-portfolio-service"

    def on_start(self):
        super().on_start()
        self.test_start_time = time.time()

        options = self.environment.parsed_options
        self.benchmark_length_minutes: int = options.benchmark_length_minutes
        self.batch_job_start_time_in_seconds = generate_random_event_time_in_seconds(
            self.benchmark_length_minutes, lower_margin_percent=50, upper_margin_percent=20)
        logging.info(
            f"Batch job will start at {self.batch_job_start_time_in_seconds} seconds into the benchmark"
        )

        self.cd_release_time_in_seconds = generate_random_event_time_in_seconds(
            self.benchmark_length_minutes, lower_margin_percent=20, upper_margin_percent=30)
        logging.info(
            f"CD release will start at {self.cd_release_time_in_seconds} seconds into the benchmark"
        )

        # Configure TLS for the Locust HTTP client
        self.client.verify = CA_PATH
        if CLIENT_CERT_TUPLE:
            self.client.cert = CLIENT_CERT_TUPLE
            
        self.client.headers.update({
            "Accept": "application/json",
        })


    @task
    def default_task(self) -> None:
         # Calculate the run time in seconds
        run_time = time.time() - self.test_start_time
        logging.debug(f"Current run time: {run_time:.2f} seconds")
        
        if not self.batch_job_started and run_time >= self.batch_job_start_time_in_seconds:
            # Run the batch job
            logging.info("Batch job started!")
            response = run_batch(self.client) 
            if response.ok:
                logging.info("Batch job completed successfully!")
                self.batch_job_started = True   
            else:
                logging.error(f"Batch job failed with status code {response.status_code}")
                logging.error(response.text)

        if not self.cd_release_deployed and run_time >= self.cd_release_time_in_seconds:
            # Deploy the CD release
            logging.info("Deploying CD release!")
            try:
                upgrade_image(self.client, self.deployment_name)
                self.cd_release_deployed = True
                logging.info("CD release deployed!")
            except Exception as e:
                logging.error(f"CD release failed: {e}")
                self.cd_release_deployed = True
