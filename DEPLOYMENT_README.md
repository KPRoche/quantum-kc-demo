# Quantum Raspberry Tie - Non-Raspberry Pi Deployment

Deploy Quantum Raspberry Tie on any system (Linux, macOS, Windows) without Raspberry Pi hardware or LED displays.

## 📦 What You Get

A complete web-based deployment of quantum circuit execution and visualization:

- 🌐 **Web Dashboard** - Modern, responsive browser interface
- 🚀 **Two Deployment Options** - Docker or local Python
- ⚡ **Fast Execution** - Local quantum simulation (no internet required)
- 📊 **Real-time Visualization** - See results as they update
- 🔌 **REST API** - Programmatic access to quantum execution
- 📁 **Persistent Storage** - Results saved for later review

## 🎯 Choose Your Installation

### 🐳 Option 1: Docker (Recommended)

**Best for:** Production, cross-platform compatibility, guaranteed isolation

```bash
# One command startup
docker-compose up --build

# Access dashboard at http://localhost:5000
```

**Pros:**
- Works everywhere (Linux, macOS, Windows)
- No Python setup needed
- Isolated environment

**Cons:**
- Requires Docker Desktop installed
- Slightly slower development iteration

### 🐍 Option 2: Local Python

**Best for:** Development, quick testing, learning

#### Linux/macOS
```bash
chmod +x start-local.sh
./start-local.sh
```

#### Windows
```bash
start-local.bat
```

**Pros:**
- Faster iteration
- Direct code access
- Minimal dependencies

**Cons:**
- Requires Python 3.9+
- Platform-specific setup
- Potential dependency conflicts

---

## 📖 Documentation

| Document | Purpose |
|----------|---------|
| **QUICKSTART.md** | 5-minute quick reference |
| **DEPLOYMENT.md** | Complete technical guide |
| **DEPLOYMENT_SUMMARY.md** | Feature overview |
| **README.md** | Original project documentation |

---

## 🎮 Using the Dashboard

### 1. Open Dashboard
```
http://localhost:5000
```

### 2. Select Configuration
- **Circuit**: 5, 12, or 16 qubit options
- **Backend**: Local simulator (default)
- **Shots**: 1-1000 repetitions

### 3. Execute
Click the **Execute** button to run

### 4. View Results
- Qubit measurement visualization
- Probability distribution
- SVG rendering
- JSON API access

---

## 📁 Deployment Artifacts

```
quantum-raspberry-tie/
├── docker-compose.yml          # One-click deployment
├── Dockerfile                  # Container specification
├── web_dashboard.py            # Main application
├── templates/dashboard.html    # Web UI
├── requirements-docker.txt     # Dependencies
├── start-local.sh              # Linux/macOS startup
├── start-local.bat             # Windows startup
├── svg/                        # Results output
└── credentials/                # IBM Quantum config
```

---

## 🔧 Common Tasks

### Accessing from Another Computer

```bash
# Find your machine IP
# Linux/macOS: hostname -I
# Windows: ipconfig

# Then visit: http://<your-ip>:5000
```

### Using Different Port

```bash
# Docker
docker run -p 8080:5000 quantum-tie:latest

# Python
# Edit web_dashboard.py, line ~200: app.run(port=8080)
```

### Viewing Results Files

```bash
# SVG outputs saved to ./svg/
# Access via: http://localhost:5000/api/svg

# JSON results
curl http://localhost:5000/api/result
```

### Customizing Circuits

1. Create your `.qasm` file
2. Copy to project root (e.g., `mycircuit.qasm`)
3. Mount in Docker or access via Python
4. Select in dashboard (requires code modification)

---

## 🔗 API Reference

### Query Execution Status
```bash
curl http://localhost:5000/api/status
```

### Submit Circuit
```bash
curl -X POST http://localhost:5000/api/execute \
  -H "Content-Type: application/json" \
  -d '{
    "qasm_file": "expt.qasm",
    "backend": "local",
    "shots": 10
  }'
```

### Get Last Result
```bash
curl http://localhost:5000/api/result
```

### Get SVG Visualization
```bash
curl http://localhost:5000/api/svg
```

---

## 🐛 Troubleshooting

### Dashboard won't load

**Problem:** `Connection refused`

**Solutions:**
1. Check container/process is running
2. Verify port 5000 isn't in use: `lsof -i :5000`
3. Try with a different port
4. Check firewall settings

### Quantum execution fails

**Problem:** "Execution failed" in dashboard

**Solutions:**
1. Start with 5-qubit circuit (simplest)
2. Try 1-10 shots first
3. Check Docker logs: `docker logs quantum-raspberry-tie`
4. Ensure QASM files exist in container

### Python module not found

**Problem:** `ImportError` with Qiskit

**Solutions:**
```bash
# Ensure venv is activated
source venv/bin/activate

# Reinstall dependencies
pip install -r requirements-docker.txt
```

### Permission denied

**Problem:** Script execution fails on Linux/macOS

**Solutions:**
```bash
chmod +x start-local.sh
```

### Port already in use

**Problem:** Error binding to port 5000

**Solutions:**
```bash
# Kill process using port
lsof -i :5000 | grep LISTEN | awk '{print $2}' | xargs kill -9

# Or use different port
docker run -p 5001:5000 quantum-tie:latest
```

---

## 🚀 Production Deployment

For deploying to production:

1. **Use reverse proxy** (nginx, Traefik)
   ```nginx
   location / {
       proxy_pass http://localhost:5000;
       proxy_set_header Host $host;
   }
   ```

2. **Enable HTTPS** with certificates
   ```bash
   # Use Let's Encrypt with Traefik
   ```

3. **Add authentication** to dashboard
   - Modify `web_dashboard.py` to add auth middleware

4. **Set resource limits**
   ```bash
   docker run --memory=1g --cpus=2 quantum-tie:latest
   ```

5. **Enable logging**
   ```yaml
   # docker-compose.yml
   logging:
     driver: "json-file"
     options:
       max-size: "10m"
   ```

See **DEPLOYMENT.md** for complete production guide.

---

## 📊 Performance

### Hardware Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| CPU | 2 cores | 4+ cores |
| RAM | 2GB | 4GB+ |
| Disk | 1GB | 5GB |
| Network | None required | Optional (IBM Quantum) |

### Execution Times

- **5-qubit, 10 shots**: ~100-200ms
- **12-qubit, 10 shots**: ~200-500ms
- **16-qubit, 10 shots**: ~500ms-2s
- **Scaling**: Linear with shot count

---

## 🔐 Security

### Docker Security
- ✅ Non-root user (`quantum:1000`)
- ✅ No privileged mode
- ✅ Minimal attack surface
- ✅ Read-only where possible

### Data Security
- ✅ Credentials stored locally only
- ✅ No data sent to cloud (unless configured)
- ✅ Results persisted locally
- ✅ No telemetry

### Production Hardening
- Use secrets management for IBM Quantum tokens
- Enable HTTPS/TLS
- Add authentication layer
- Run behind firewall
- Monitor logs for errors

---

## 🎓 Learning

### Getting Started
1. Read **QUICKSTART.md**
2. Run `docker-compose up --build`
3. Explore the dashboard
4. Try different circuits and settings

### Understanding the Code
- **web_dashboard.py** - REST API and Qiskit integration
- **templates/dashboard.html** - Frontend JavaScript
- **Dockerfile** - Container specification
- **requirements-docker.txt** - Dependencies

### IBM Quantum Integration
See **DEPLOYMENT.md** section on "Using IBM Quantum Cloud Backend"

---

## 📞 Support

### Getting Help
1. Check **Troubleshooting** section above
2. Review **DEPLOYMENT.md** for advanced topics
3. Check Docker logs: `docker logs quantum-raspberry-tie`
4. Review Python logs: standard output from `start-local.sh`

### Known Limitations
- SVG rendering limited to 8x8 matrix
- Local Aer simulator is single-threaded
- No GUI joystick controls (web buttons instead)
- No physical accelerometer support

### Feature Requests
Suggested enhancements in **DEPLOYMENT.md** "Advanced Configuration" section

---

## 📜 License

See `LICENSE` file in project root

---

## 🏆 Acknowledgments

- Original Quantum Raspberry Tie project
- Qiskit framework (IBM)
- Flask web framework
- Open source community

---

## 🔄 Version History

- **v1.0** (March 2025) - Initial non-RPi deployment package
- Based on Quantum Raspberry Tie v7.1

---

**Ready to get started?** See **QUICKSTART.md** for your platform!
