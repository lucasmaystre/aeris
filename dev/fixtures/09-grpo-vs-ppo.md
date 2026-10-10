# Notes on RL: GRPO vs PPO
Tags: #research/rl

GRPO drops the value network: the baseline is the mean reward of a group of samples for the same
prompt, so the advantage is `(r - mean(r)) / std(r)`. Cheaper than PPO, but noisier with small
groups.

> With verifiable rewards and groups of 16 or more, the variance is usually acceptable.

Open question: does adaptive difficulty filtering help more than a larger group size?
