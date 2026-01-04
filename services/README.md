# Services

This directory contains the source code and configuration for the services that are deployed on the home automation
server.

## Docker Compose Process

The services are managed using `docker compose`. The main `docker-compose.yml` file is located in this directory.

### Local Testing

To test the services locally, you can use `docker compose`. Make sure you have Docker and `docker compose` installed on
your local machine.

Run the following command in this directory (`services`):

```bash
docker compose up
```

This will build the images (if they don't exist locally) and start all the services defined in the `docker-compose.yml`
file.

#### Local Overrides for Testing

For local testing, you can use a `docker-compose.dev.yml` file to adjust configurations without affecting the remote deployment. This is particularly useful for:

*   **Stubbing Devices:** If you don't have the physical Zigbee or Z-Wave hardware connected, the override file maps the device paths to `/dev/null`, allowing the containers to start.
*   **Local Volume Paths:** The main `docker-compose.yml` uses absolute paths (e.g., `${VOLUMES_DIR}/home-assistant/config`) for remote deployment. For local testing, the override file maps these to paths within a centralized `volumes` directory at the project root (e.g., `../volumes/home-assistant/config`) so data is stored outside the `services` directory.

1.  **`docker-compose.dev.yml`:** In this same `services` directory, you will find a file named `docker-compose.dev.yml`.

2.  When you run `docker compose up `, TODO research

3.  **Git Ignore:** Remember that `docker-compose.dev.yml` is typically added to `.gitignore` as it contains local-specific configurations. Also, the `volumes` directory itself should be added to `.gitignore`.

### Remote Deployment

To deploy the services to the remote host (`mars`), you typically use a combination of Ansible for configuration management and Docker contexts for service deployment.

#### Configuration Deployment (Ansible)

Configuration changes (e.g., Home Assistant settings, Zigbee2MQTT configurations) are deployed to the remote host using Ansible. This ensures that the correct configuration files are in place before the Docker services are started or restarted.

For detailed instructions on deploying configurations, refer to the `copy-config.yml` playbook in the [Infrastructure Management README](../../infrastructure/mars/ansible/README.md).

#### Docker Service Deployment (Docker Context)

To deploy the Docker services themselves, you can use a Docker context. This allows you to control the remote Docker engine from your local machine. Note that the main `docker-compose.yml` uses the `${VOLUMES_DIR}` environment variable for volume paths, which is set on the remote host.

#### Pre-Deployment Backup (Recommended)

Before deploying, it's highly recommended to create a backup of your critical service data directly on the remote host. This ensures that if anything goes wrong during deployment, you have a recent snapshot of your configurations and data.

For instructions on how to perform a remote backup using Ansible, please refer to the [Infrastructure Management README](../../infrastructure/mars/ansible/README.md).

#### Restoring from Backup

In case of data loss or corruption, you can restore your critical service data from a previous backup using Ansible.

For instructions on how to restore from a backup using Ansible, please refer to the [Infrastructure Management README](../../infrastructure/mars/ansible/README.md).

#### 1. Create a Docker Context

First, create a new Docker context that points to your remote host via SSH.

```bash
docker context create mars --docker "host=ssh://<your_user>@mars.local"
```

Replace `<your_user>` with your username on the `mars` server.

#### 2. Switch to the Remote Context

Before deploying, switch to the newly created context:

```bash
docker context use mars
```

Now, any Docker command you run will be executed on the `mars` server.

#### 3. Deploy the Services

To deploy the services, run the following command from this directory (`services`):

```bash
docker compose up -d
```

This will start the services in detached mode.

#### Image Management

When you deploy to a remote host, the Docker images for your services need to be available on that host. You have a few options:

*   **Local Builds (Ansible Managed):** If `local_build: true` is set in your Ansible configuration (e.g., in `infrastructure/mars/ansible/copy-config.yml`), images are built on the control machine and then transferred as tarballs to the remote host, where they are loaded. This is efficient for development as it leverages local build resources.

*   **Remote Builds:** You can build the images directly on the remote host by running:
    ```bash
    docker compose up --build -d
    ```
    This will send the build context from your local machine to the remote host and build the images there. This is convenient but can be slow if your project has a lot of files.

*   **Use a Docker Registry (Recommended):** You can push your images to a Docker registry (like Docker Hub or a private registry). The remote host will then pull the images from the registry. This is the most common and efficient method for production deployments.

*   **Save and Load Images:** You can save your local images as `.tar` files (`docker save`), copy them to the remote host (e.g., with `scp`), and then load them on the remote host (`docker load`).

#### 4. Switch Back to Local Context

Once you are done with the remote deployment, you can switch back to your local Docker context:

```bash
docker context use default
```
