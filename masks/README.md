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
`fslcc`. `code/run_dual_regression_smith09.sh` independently resamples the
same ordered maps to the input-data grid. Previously resliced maps from other
projects should not be reused.

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

## Brain Reward Signature

`BrainRewardSignature_2mm.nii` is the signed, continuous multivariate Brain
Reward Signature from Speer et al. (2023), *NeuroImage*, 271, 119990,
https://doi.org/10.1016/j.neuroimage.2023.119990 (PMID 36878456). It has the
same 91 x 109 x 91, 2-mm MNI grid as the Smith09 file. Its 163 non-finite
voxels are set to zero in the generated analysis copy; the original source
image is retained unchanged here. SHA-256:

```text
154a36556a45fbf04950ed1fd9d7ed174f1aad54d5fbbe06f9047eee6b55099c
```

With `--include-reward`, `code/run_dual_regression_smith09.sh` appends this
map after the ten Smith09 maps. The reward signature is therefore component
11 in `dual-regression_smith09-reward_*.dr`.
