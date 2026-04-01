# Quantum Raspberry Tie - Non-RPi Deployment Guide

This guide covers deploying Quantum Raspberry Tie on non-Raspberry Pi hardware (Linux, macOS, Windows with WSL, etc.) without requiring any LED display hardware.

## Quick Start with Docker (Recommended)

### Prerequisites
- Docker and Docker Compose installed
- ~2GB disk space for container image
- No GPIO or hardware dependencies needed

### Deployment

1. **Clone or download the repository:**
   ```bash
   cd quantum-raspberry-tie
   ```

2. **Build and start the container:**
   ```bash
   docker-compose up --build
   ```

3. **Access the dashboard:**
   Open your browser to `http://localhost:5000`

4. **Stop the container:**
   ```bash
   docker-compose down
   ```

## Docker Details

### Building the Image Manually

```bash
docker build -t quantum-tie:v0.2.9 .
```

### Running Without Docker Compose

```bash
docker run -it --rm \
  -p 5000:5000 \
  -v $(pwd)/svg:/app/svg \
  -v $(pwd)/credentials:/app/credentials \
  quantum-tie:v0.2.9
```

### Container Environment Variables

- `QUANTUM_DISPLAY_MODE`: Display mode (default: `svg`)
- `QUANTUM_BACKEND`: Backend choice (default: `local`)
- `QUANTUM_QUBITS`: Number of qubits (default: `5`)
- `FLASK_ENV`: Flask environment (default: `production`)

### Accessing from Other Machines

Replace `localhost` with the container host IP:
```
http://<your-machine-ip>:5000
```

## Web Dashboard Features

### Main Interface
- **Control Panel**: Select quantum circuit, backend, and shot count
- **Results Panel**: View measured qubit states and probability distributions
- **SVG Visualization**: Real-time quantum state visualization

### Supported Circuits

1. **5-Qubit Random Number Generator** (default)
   - Simple Hadamard gates creating superposition
   - Fast execution

2. **12-Qubit Hex Pattern**
   - Larger circuit demonstrating heavier computational load
   - Shows pattern layout similar to IBM heavy-hex processors

3. **16-Qubit Pattern**
   - Large circuit for testing performance
   - Demonstrates scaling

### Backend Options

- **Local Simulator (Aer)** - Default, no internet required
- **Fake Backend** - Simulates real processor characteristics locally

## Python Virtual Environment Setup (Alternative)

If you prefer not to use Docker:

### Prerequisites
- Python 3.9+
- pip package manager
- virtualenv (optional but recommended)

### Installation

1. **Create virtual environment:**
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements-docker.txt
   ```

3. **Run the dashboard:**
   ```bash
   python web_dashboard.py
   ```

4. **Access the dashboard:**
   Open `http://localhost:5000`

## Using IBM Quantum Cloud Backend (Optional)

To use real IBM Quantum processors or cloud simulators:

### Setup

1. Create an account at https://quantum.ibm.com
2. Get your API token from your account settings
3. Create `credentials/config.json`:
   ```json
   {
     "ibm_quantum_token": "your_token_here",
     "ibm_quantum_url": "https://auth.quantum.ibm.com/api"
   }
   ```

### Docker with IBM Quantum

Mount your credentials when starting the container:

```bash
docker run -it --rm \
  -p 5000:5000 \
  -v $(pwd)/credentials:/app/credentials \
  -v $(pwd)/svg:/app/svg \
  quantum-tie:v0.2.5
```

Then select "IBM Quantum" backend in the dashboard (when implemented).

## Output Files

The application generates output in these locations:

### Docker Container
- **SVG Results**: `/app/svg/pixels.html` (mounted to `./svg/`)
- **Credentials**: `/app/credentials/config.json` (mounted to `./credentials/`)

### Python Virtual Environment
- **SVG Results**: `./svg/pixels.html`
- **Credentials**: `./credentials/config.json`

## Performance Considerations

### Docker Performance

- **Build time**: ~2-3 minutes (first time only)
- **Startup time**: ~5-10 seconds
- **Execution time**: Depends on circuit size
  - 5-qubit: ~100-200ms
  - 12-qubit: ~200-500ms
  - 16-qubit: ~500ms-2s

### Optimization Tips

1. **Use Local Simulator**: Fastest option, no internet needed
2. **Adjust Shot Count**: Lower shots = faster execution (min: 1, max: 1000)
3. **Container Size**: Multi-stage build keeps image ~800MB-1GB

## Troubleshooting

### Dashboard Not Accessible

**Problem**: `Connection refused` or `Cannot reach localhost:5000`

**Solutions**:
1. Verify container is running: `docker ps`
2. Check port isn't in use: `lsof -i :5000` (or `netstat -an | findstr 5000` on Windows)
3. Use machine IP if accessing from another computer
4. Check Docker logs: `docker logs quantum-raspberry-tie`

### Quantum Execution Errors

**Problem**: "Execution failed" error in dashboard

**Solutions**:
1. Ensure Qiskit is properly installed
2. Try with fewer shots (start with 1-10)
3. Check container logs for details
4. Verify QASM files exist in container: `docker exec quantum-raspberry-tie ls -la`

### Permission Errors

**Problem**: Cannot write to credentials or svg directories

**Solutions**:
1. Ensure directories exist: `mkdir -p credentials svg`
2. Set permissions: `chmod 755 credentials svg`
3. On Docker: Container runs as `quantum` user (UID 1000)

### Memory Issues

**Problem**: Container crashes or becomes unresponsive

**Solutions**:
1. Increase Docker memory limit in Docker Desktop settings
2. Use smaller circuits (5-qubit instead of 16-qubit)
3. Reduce shot count
4. Check system resources: `docker stats quantum-raspberry-tie`

## Advanced Configuration

### Custom Dockerfile

Modify `Dockerfile` to:
- Change base Python version
- Add additional libraries
- Modify startup command

### Custom QASM Circuits

1. Create your QASM file (e.g., `mycircuit.qasm`)
2. Place in project root
3. Modify `docker-compose.yml` to mount it:
   ```yaml
   volumes:
     - ./mycircuit.qasm:/app/mycircuit.qasm
   ```
4. Select it in the dashboard (requires dashboard modification)

### Production Deployment

For production use:

1. **Use a reverse proxy** (nginx, Traefik)
2. **Enable HTTPS** with certificates
3. **Add authentication** to the dashboard
4. **Use persistent volumes** for credentials
5. **Set resource limits** on containers
6. **Enable logging** and monitoring
7. **Run behind a firewall**

Example with nginx:
```nginx
server {
    listen 80;
    server_name quantum.example.com;

    location / {
        proxy_pass http://localhost:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

## API Endpoints

The web dashboard uses these REST API endpoints:

### Status
- `GET /api/status` - Get current execution status
- Returns: `{running, last_result, status, message, ...}`

### Execution
- `POST /api/execute` - Submit circuit for execution
- Body: `{qasm_file, backend, shots}`
- Returns: `{status: "submitted"}`

### Results
- `GET /api/result` - Get last execution result
- `GET /api/svg` - Get SVG visualization as HTML

### Configuration
- `GET /api/config` - Get stored configuration
- `POST /api/config` - Save configuration

## Original Raspberry Pi Version

For deployment on actual Raspberry Pi hardware with LED displays, see the original instructions in `README.md`:
- SenseHat LED display support
- NeoPixel array support
- Joystick controls
- Orientation detection

## Support and Issues

For issues or questions:
1. Check the troubleshooting section above
2. Review Docker/container logs
3. Verify all dependencies are installed
4. Check available disk space and system resources
5. Review the original `README.md` for Qiskit setup issues

## License

See `LICENSE` file for licensing information.
