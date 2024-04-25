# -*- coding: UTF-8 -*-
# * Particle Filter realized by JinXiangLai at 2024-04-24 22:10

from turtle import color
import numpy as np
from math import pi, cos, sin, sqrt
import matplotlib.pyplot as plt
from scipy.stats import multivariate_normal
import copy
import time

# Right-Front-Up Coordinate，wheel speed direction along with Y axis
WHEEL_BASE = 0.3   # m
SAMPLE_TIME = 0.05 # ms
RADIUS = 1.0 # m
DEGREE2RAD = pi / 180
VEL_STD = 0.1
# Sampling directly from the target distribution, all particles have a weight of 1
SAMPLE_FROM_TARGET_DISTRIBUTION = 0 
LASER_POSE_OBV = []
RESAMPLE_RATIO = 0.9
MEASURE_NOISE = np.array([
                [sqrt(VEL_STD**2 + VEL_STD**2) / WHEEL_BASE, 0, 0],
                [0, sqrt(VEL_STD**2 + VEL_STD**2)/2, 0],
                [0, 0, sqrt(VEL_STD**2 + VEL_STD**2 / 2)]
            ])


def R_z(x, is_rad=True) -> np.ndarray:
    if not is_rad:
        x = x * DEGREE2RAD
    return np.array([
        [cos(x), -sin(x)],
        [sin(x), cos(x)],
    ])


# Generate wheel speed dataset for propagate progress
def SampleCircle(sample_num, vr_list:list, vl_list:list):
    px_last = RADIUS
    py_last = 0.0
    theta_last = 0 * DEGREE2RAD
    d_theta = 360 / sample_num * DEGREE2RAD
    px_list = [px_last]
    py_list = [py_last]
    for i in range(sample_num):
        theta = theta_last + d_theta
        px = cos(theta) * RADIUS
        py = sin(theta) * RADIUS
        w = d_theta / SAMPLE_TIME
        vx = (px - px_last) / SAMPLE_TIME
        vy = (py - py_last) / SAMPLE_TIME
        v_w = np.array([vx, vy])
        v_y = np.linalg.inv(R_z(theta_last)) @ v_w
        v = np.linalg.norm(v_y)
        
        '''
            vr - vl = w * WHEEL_BASE
            vr + vl = 2 * v
        '''
        vr = w * WHEEL_BASE / 2 + v
        vl = v - w * WHEEL_BASE / 2
        vr_list.append(vr)
        vl_list.append(vl)

        px_last = px
        py_last = py
        theta_last = theta

        px_list.append(px)
        py_list.append(py)


# Generate ground truth pose for update progress
def GenerateCircle(vr_list:list, vl_list:list):
    theta = 0 * DEGREE2RAD
    data_num = len(vr_list)
    x_list = [RADIUS]
    y_list = [0]
    p_w_last = np.array([RADIUS, 0])
    for i in range(data_num):
        v = (vr_list[i] + vl_list[i]) / 2
        v_y = np.array([0, v])
        v_w = R_z(theta) @ v_y

        # update pos
        p_w = p_w_last + v_w * SAMPLE_TIME
        x_list.append(p_w[0])
        y_list.append(p_w[1])

        # update orientation
        theta += (vr_list[i] - vl_list[i]) / WHEEL_BASE * SAMPLE_TIME
        p_w_last = p_w

        LASER_POSE_OBV.append(np.array([theta, p_w[0], p_w[1]]))


class Particle:
    def __init__(self, pose:np.ndarray, weight):
        # θ, x, y
        self.pose_ = pose.copy()
        self.weight_ = weight
    
    def Predict(self, vr, vl, dt):
        v = (vr + vl) / 2.0
        v_y = np.array([0, v])
        w = (vr - vl) / WHEEL_BASE
        self.pose_[1:] += R_z(self.pose_[0]) @ v_y * dt
        self.pose_[0] +=  w * dt

    def Update(self, measurement, landmark) -> None:
        # 需要根据地图点来更新pose???
        pass


class Map:
    def __init__(self, w:float, h:float) -> None:
        self.width_ = w
        self.height_ = h
        self.landmarks_ = [np.array([-w, -h]), np.array([w, -h]),
                            np.array([w, h]), np.array([-w, h])]
        # 为了简单起见，假定机器人都能按顺序观测到4个地图点
        self.landmark_num_ = len(self.landmarks_)


class ParticleManager:
    def __init__(self, particle_num:int, map: Map) -> None:
        self.weights_ = []
        self.traj_ = []
        self.num_ = particle_num
        self.max_resample_threshold_ = self.num_ * RESAMPLE_RATIO
        self.map_ = map

        self.particles_ = []
        for i in range(particle_num):
            theta = np.random.rand() * 2 * pi
            pos_x = np.random.rand() * map.width_
            pos_y = np.random.rand() * map.height_
            self.particles_.append( Particle(np.array([theta, pos_x, pos_y]), 1) )
            self.weights_.append(1)
    
    def SetNewParticleSet(self, new_p: list):
        self.particles_ = new_p
        new_weight = 1.0 / self.num_
        for i in range(self.num_):
           self.particles_[i].weight_ = new_weight
           self.weights_[i] =  new_weight
    
    def NormlizeWeight(self) -> None:
        diff = abs(np.sum(self.weights_) - 1.0)
        if diff > 1e-20 and diff < 1e-19:
            return
            
        for i in range(self.num_):
            self.weights_[i] = self.particles_[i].weight_
        self.weights_ = np.array(self.weights_) / np.sum(self.weights_)
        self.weights_ = self.weights_.tolist()
        for i in range(self.num_):
            self.particles_[i].weight_ = self.weights_[i]
    
    def UpdateCurrentMeanPose(self) -> None:
        pose = np.zeros(3)
        for i in range(self.num_):
            pose += self.particles_[i].pose_ * self.weights_[i] 
        self.traj_.append(pose)
    
    def NeedResample(self) -> bool:
        sum_square_weight = 0
        for w in self.weights_:
            sum_square_weight += w**2
        
        Neff = 1 / sum_square_weight
        return Neff < self.max_resample_threshold_

    def RouletteSelect(self):
        self.NormlizeWeight()
        sum_weights = [self.weights_[0]]
        for i in range(1, self.num_):
            sum_weights.append(sum_weights[i-1] + self.weights_[i])

        new_p = []
        for i in range(self.num_):
            sum_weight = np.random.rand()
            for j in range(self.num_):
                if sum_weight < sum_weights[j]:
                    p = copy.deepcopy(self.particles_[j])
                    new_p.append(p)
                    break
        
        self.SetNewParticleSet(new_p)
        
    def UpdateParticleWeightsAndCurrentPose(self, weight_list):
        # Normlize weights
        weight_list = np.array(weight_list) / np.sum(weight_list)
        for i in range(self.num_):
            self.particles_[i].weight_ *= weight_list[i]
            #self.particles_[i].weight_ = weight_list[i]

        self.NormlizeWeight()
        self.UpdateCurrentMeanPose()

    def CalculateWeight(self, pose : np.ndarray, measurement:list) -> float:
        R_wv = R_z(pose[0])
        t_wv = pose[1:]
        point_dist_diff = []
        for i in range(self.map_.landmark_num_):
            p = R_wv @ measurement[i] + t_wv
            diff = self.map_.landmarks_ - p
            point_dist_diff.append(diff)

        # 权重定义为距离和倒数是否合理？
        dist_diff = []
        for i in range(self.map_.landmark_num_):
            dist_diff.append(1.0 / np.linalg.norm(point_dist_diff[i]))
        return sum(dist_diff)

    def GenerateTrueMeasurement(self, true_pose:np.ndarray) -> list:
        R_vw =  R_z(true_pose[0]).transpose()
        t_vw = -R_vw @ true_pose[1:]
        measurement = []
        for i in range(self.map_.landmark_num_):
            p = R_vw @ self.map_.landmarks_[i] + t_vw
            measurement.append(p)
        return measurement

    def DrawParticles(self, true_pose) -> None:
        p_x = []
        p_y = []
        for i in range(self.num_):
            p_x.append(self.particles_[i].pose_[1])
            p_y.append(self.particles_[i].pose_[2])
        plt.scatter(p_x, p_y, color='blue')
        plt.scatter(true_pose[1], true_pose[2], color='red')
        plt.show(block=True)


def main(sample_num, particle_num):
    vr_list = []
    vl_list = []
    SampleCircle(sample_num, vr_list, vl_list)
    GenerateCircle(vr_list, vl_list)

    map = Map(RADIUS * 2, RADIUS * 2)
    
    init_pose_true = np.array([0., RADIUS/2, RADIUS/2])
    manager = ParticleManager(particle_num, map)
    particle_true = Particle(init_pose_true, 1.)
    
    start_t = time.time()

    # predict pose and update weight
    for i in range(sample_num):
        vr = vr_list[i]
        vl = vl_list[i]
        particle_true.Predict(vr, vl, SAMPLE_TIME)
        measurement = manager.GenerateTrueMeasurement(particle_true.pose_)
        # 给测量添加上噪声

        weight_list = [] # probability density value
        for j in range(particle_num):
            p = manager.particles_[j]
            # 只有添加噪声，才能让粒子最终收敛，这一步是核心
            noise_r = np.random.normal(0, VEL_STD)
            noise_l = np.random.normal(0, VEL_STD)
            vr_j = vr + noise_r
            vl_j = vl + noise_l

            # propagate pos, orientation, weight
            p.Predict(vr_j, vl_j, SAMPLE_TIME)

            # predict weight
            weight = manager.CalculateWeight(p.pose_, measurement)
            weight_list.append(weight)

        
        # Update paticles weight and current mean pose
        manager.UpdateParticleWeightsAndCurrentPose(weight_list)

        # Draw Current Result
        #if i % 20 == 0:
        # manager.DrawParticles(particle_true.pose_)
        
        # resample
        if manager.NeedResample():
            print("resample at step %d"%(i))
            manager.RouletteSelect()
    end_t = time.time()
    print("Filter spend time %.6f s"%(end_t - start_t))
    manager.DrawParticles(particle_true.pose_)
    

if __name__ == "__main__":
    sample_num = 1800
    particle_num = 2000
    main(sample_num, particle_num)
