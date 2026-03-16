# Quick Start Guide - Non-RPi Deployment

## 🐳 Option 1: Docker (Easiest)

### One-liner startup:
```bash
docker-compose up --build
```

Then open: **http://localhost:5000**

### To stop:
```bash
docker-compose down
```

---

## 🐍 Option 2: Python Virtual Environment (Local)

### Linux/macOS:
```bash
chmod +x start-local.sh
./start-local.sh
```

### Windows:
```bash
start-local.bat
```

Then open: **http://localhost:5000**

---

## 🎮 Using the Dashboard

1. **Select a circuit**: Choose 5, 12, or 16 qubit circuit
2. **Pick a backend**: Local simulator (default, no internet needed)
3. **Set shots**: Number of times to run (1-1000)
4. **Click Execute**: Run the quantum circuit
5. **View results**: See measured qubits and probability distribution

---

## 📁 Key Files

| File | Purpose |
|------|---------|
| `Dockerfile` | Container image specification |
| `docker-compose.yml` | Easy multi-container setup |
| `web_dashboard.py` | Main web server application |
| `templates/dashboard.html` | Browser-based UI |
| `requirements-docker.txt` | Python package dependencies |
| `DEPLOYMENT.md` | Detailed deployment guide |

---

## 🔧 Troubleshooting

### Docker not starting?
```bash
# Check if port 5000 is in use
lsof -i :5000

# Use a different port
docker run -p 5001:5000 quantum-tie:latest
```

### Permission denied on start-local.sh?
```bash
chmod +x start-local.sh
```

### Quantum circuit execution fails?
- Start with 5-qubit circuit (simplest)
- Try with 1-10 shots first
- Check container logs: `docker logs quantum-raspberry-tie`

---

## 🌐 Access from Another Computer

Replace `localhost` with your machine's IP:

```
http://<your-ip>:5000
```

To find your IP:
- **Linux/macOS**: `hostname -I` or `ifconfig`
- **Windows**: `ipconfig` (look for IPv4 Address)

---

## 📊 What You Can Do

✅ Run quantum circuits locally (no internet needed)
✅ View real-time results visualization
✅ Adjust circuit parameters
✅ Export SVG output
✅ Multiple circuit sizes (5, 12, 16 qubits)

---

## 🚀 Next Steps

- See `DEPLOYMENT.md` for advanced configuration
- Check `README.md` for original Raspberry Pi setup
- Read `web_dashboard.py` to understand the API

---

## 💡 Tips

- **Fastest execution**: Use 5-qubit circuit with 10 shots
- **Most interesting**: Use 5-qubit circuit with 100 shots and the hex (12-qubit) display
- **Most qubits**: Use 16-qubit circuit (slower)
- **Offline mode**: Local simulator requires no internet
- **Persistent storage**: Results saved in `./svg/` directory

---

Enjoy exploring quantum computing! 🌌
