# Third-Party Dependencies

CARES relies on the following open-source libraries. We gratefully acknowledge
their authors and contributors.

| Library | Version | License | Usage in CARES |
|---|---|---|---|
| [NumPy](https://numpy.org/) | ≥ 1.24.0 | BSD-3-Clause | Vector math, UAV state arrays, EKF matrices |
| [SciPy](https://scipy.org/) | ≥ 1.11.0 | BSD-3-Clause | Fiedler eigenvalue computation (`scipy.sparse.linalg`), Laplacian |
| [Pygame](https://pygame.org/) | ≥ 2.5.0 | LGPL-2.1 | Interactive simulation visualization (optional) |
| [Matplotlib](https://matplotlib.org/) | ≥ 3.7.0 | PSF-based | Monte Carlo result plots, performance visualization |
| [PyYAML](https://pyyaml.org/) | ≥ 6.0 | MIT | Scenario and config file parsing |
| [FastAPI](https://fastapi.tiangolo.com/) | ≥ 0.110.0 | MIT | Web dashboard backend (optional) |
| [Uvicorn](https://www.uvicorn.org/) | ≥ 0.29.0 | BSD-3-Clause | ASGI server for FastAPI (optional) |
| [websockets](https://websockets.readthedocs.io/) | ≥ 12.0 | BSD-3-Clause | Real-time telemetry streaming (optional) |

## Algorithmic References

The following academic works directly influenced the CARES architecture:

1. **CBBA**: Choi, H.-L., Brunet, L., & How, J. P. (2009). "Consensus-Based Decentralized Auctions for Robust Task Allocation." *IEEE Transactions on Robotics*, 25(4), 912-926.

2. **ORCA**: van den Berg, J., Guy, S. J., Lin, M., & Manocha, D. (2011). "Reciprocal n-Body Collision Avoidance." *Robotics Research*, Springer.

3. **CBF for Connectivity**: Capelli, B., & Sabattini, L. (2020). "Connectivity Maintenance for Multi-Robot Systems via CBF." *IEEE Control Systems Letters*.

4. **MBB Handover**: 3GPP TS 38.300 §9.2.3: Make-Before-Break Handover in 5G NR.

5. **EKF for Multi-UAV**: Bar-Shalom, Y., Li, X.-R., & Kirubarajan, T. (2001). *Estimation with Applications to Tracking and Navigation*. Wiley.

6. **Persistent Charging**: Sujit, P.B. et al. (2025). "Persistent Robot Charging Problem." *IEEE Robotics and Automation Letters*.

7. **Event-Driven CBBA**: Sujit, P.B. et al. "Event-Driven CBBA for Communication-Constrained Multi-Robot Systems."

