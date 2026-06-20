# Smith09 Resting-State Networks

`PNAS_Smith09_rsn10.nii.gz` is the original 4D set of 10 resting-state
network maps distributed by FMRIB:

https://www.fmrib.ox.ac.uk/datasets/brainmap+rsns/

The image has a 91 x 109 x 91 grid, 2-mm isotropic voxels, and 10 volumes.
SHA-256:

```text
dc0e5213014476e460f7badd8f027c28177186c8346717ddc1b740f42c54fca7
```

The maps are kept in their original grid here. `code/match_smith09.sh`
resamples each map to the corresponding group MELODIC grid before running
`fslcc`; previously resliced maps from other projects should not be reused.

The volume order used by the matching summary is:

1. Primary visual
2. Occipital pole
3. Lateral visual
4. Default mode network (DMN)
5. Cerebellum
6. Sensorimotor
7. Auditory
8. Executive control network (ECN)
9. Right frontoparietal network (right FPN)
10. Left frontoparietal network (left FPN)

Please cite Smith et al. (2009), *PNAS*, 106(31), 13040-13045,
https://doi.org/10.1073/pnas.0905267106.
