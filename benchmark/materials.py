"""Material property database for FEA evaluation."""

# All stress values in MPa, density in kg/m³
MATERIALS: dict[str, dict] = {
    "pla": {
        "youngs_modulus_mpa": 3500.0,
        "poisson_ratio": 0.35,
        "yield_stress_mpa": 50.0,
        "density_kg_m3": 1240.0,
        "label": "PLA (FDM, 100% infill)",
    },
    "petg": {
        "youngs_modulus_mpa": 2100.0,
        "poisson_ratio": 0.38,
        "yield_stress_mpa": 40.0,
        "density_kg_m3": 1270.0,
        "label": "PETG (FDM, 100% infill)",
    },
    "aluminum_6061": {
        "youngs_modulus_mpa": 68900.0,
        "poisson_ratio": 0.33,
        "yield_stress_mpa": 276.0,
        "density_kg_m3": 2700.0,
        "label": "Aluminum 6061-T6",
    },
}


def get(material: str) -> dict:
    if material not in MATERIALS:
        raise ValueError(f"Unknown material '{material}'. Valid: {list(MATERIALS)}")
    return MATERIALS[material]
