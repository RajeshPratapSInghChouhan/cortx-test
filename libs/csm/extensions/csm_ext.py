#Copyright (c) 2022 Seagate Technology LLC and/or its Affiliates
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.
#
# For any questions about this software or licensing,
# please email opensource@seagate.com or cortx-questions@seagate.com.
#
"""Test library for load testing related operations."""
import time
import logging
import random
from commons.utils import config_utils
from commons.constants import  K8S_SCRIPTS_PATH, K8S_PRE_DISK, POD_NAME_PREFIX
from commons.constants import LOCAL_SOLUTION_PATH
from libs.prov.prov_k8s_cortx_deploy import ProvDeployK8sCortxLib
from libs.ha.ha_common_libs_k8s import HAK8s
import yaml

class CSMExt():
    """CSMExt is creating object and extending functionality of the ProvDeployK8sCortxLib"""
    def __init__(self, master, workers, hlth_master):
        self.master = master
        self.workers = workers
        self.hlth_master = hlth_master
        self.log = logging.getLogger(__name__)
        self.deploy_lc_obj = ProvDeployK8sCortxLib()
        self.update_seconds = 60
        self.ha_obj = HAK8s()
        self.restore_method = None

    def copy_sol_file_local(self):
        self.log.info("Copy solution.yaml from %s to local path %s", K8S_SCRIPTS_PATH, LOCAL_SOLUTION_PATH)
        remote_sol_path = K8S_SCRIPTS_PATH + "solution.yaml"
        solution_path = self.master.copy_file_to_local(remote_path=remote_sol_path,local_path=LOCAL_SOLUTION_PATH)
        return solution_path

    def update_csm_res_limit(self, m1:str, m2:str, c1:str, c2:str):
        """
        Update CSM resource limits
        :param m1: memory requests
        :param m1: memory limits
        :param c1: cpu requests
        :param c2: cpu limits
        """
        local_sol_path = LOCAL_SOLUTION_PATH
        remote_sol_path = K8S_SCRIPTS_PATH + 'solution.yaml'
        self.log.info("Path for solution yaml on remote node: %s", remote_sol_path)
        solution_path = self.master.copy_file_to_local(remote_path=remote_sol_path,
                                                               local_path=local_sol_path)
        self.log.info(solution_path)
        with open(local_sol_path, 'rb') as yaml_file:
            conf = yaml.safe_load(yaml_file)
        self.log.info("Printing solution yaml contents: %s", conf)
        parent_key = conf['solution']  # Parent key
        common = parent_key['common']
        resource = common['resource_allocation']
        control_res = resource['control']['agent']['resources']
        self.log.info("Changing the resource limit in solution.yaml...")
        self.log.info("Changing M1 value to: %s", m1)
        control_res['requests']['memory'] = m1
        self.log.info("Changing M2 value to: %s", m2)
        control_res['limits']['memory'] = m2
        self.log.info("Changing C1 value to: %s", c1)
        control_res['requests']['cpu'] = c1
        self.log.info("Changing C2 value to: %s", c2)
        control_res['limits']['cpu'] = c2
        noalias_dumper = yaml.dumper.SafeDumper
        noalias_dumper.ignore_aliases = lambda self, data: True
        with open(local_sol_path, 'wb') as soln:
            yaml.dump(conf, soln, default_flow_style=False,
                      sort_keys=False, Dumper=noalias_dumper)
            soln.close()
        resp = self.master.copy_file_to_remote(local_sol_path, remote_sol_path)
        return resp

    def read_csm_res_limit(self):
        """
        Read CSM resource limits
        """
        self.log.info("Reading the resource limit in solution.yaml...")
        sol_yaml = config_utils.read_yaml(LOCAL_SOLUTION_PATH)
        assert sol_yaml[0], f"Failed to read {LOCAL_SOLUTION_PATH}"
        csm_res = sol_yaml[1]['solution']['common']['resource_allocation']['control']['agent']['resources']
        m1 = csm_res['requests']['memory']
        self.log.info("M1 value: %s", m1)
        m2 = csm_res['limits']['memory']
        self.log.info("M2 value: %s", m2)
        c1 = csm_res['requests']['cpu']
        self.log.info("M1 value: %s", c1)
        c2 = csm_res['limits']['cpu']
        self.log.info("M2 value: %s", c2)
        return m1,m2,c1,c2

    def destroy_prep_deploy_cluster(self, expect_fail=None):
        """
        Destroy the cluster,
        Run the prereq script
        Deploy the cluster
        """
        self.log.info("[Start] Redeploy the setup...")
        self.log.info("[Cleanup: Destroying the cluster ")
        resp = self.deploy_lc_obj.destroy_setup(self.master, self.workers, K8S_SCRIPTS_PATH)
        assert resp[0], resp[1]
        self.log.info("Cleanup: Cluster destroyed successfully")

        self.log.info("Cleanup: Setting prerequisite")
        self.deploy_lc_obj.execute_prereq_cortx(self.master, K8S_SCRIPTS_PATH, K8S_PRE_DISK)
        for node in self.workers:
            self.deploy_lc_obj.execute_prereq_cortx(node, K8S_SCRIPTS_PATH, K8S_PRE_DISK)
        self.log.info("Cleanup: Prerequisite set successfully")

        self.log.info("Cleanup: Deploying the Cluster")
        resp_cls = self.deploy_lc_obj.deploy_cluster(self.master, K8S_SCRIPTS_PATH)
        if expect_fail is not None:
            assert expect_fail in resp_cls[1], "Deployment Error message check failed"
        else:
            assert resp_cls[0], resp_cls[1]
            self.log.info("Cleanup: Cluster deployment successfully")

            self.log.info("[Start] Sleep %s", self.update_seconds)
            time.sleep(self.update_seconds)
            self.log.info("[End] Sleep %s", self.update_seconds)

            self.log.info("Cleanup: Check cluster status")
            resp = self.ha_obj.poll_cluster_status(self.master)
            assert resp[0], resp[1]
            self.log.info("Cleanup: Cluster status checked successfully")
        self.log.info("[End] Redeploy the setup...")

    def delete_data_pod(self):
        """
        Degrade cluster safely by deleting the last data pod from a set
        :return str set_name: sts set name from pod was deleted
        :return int num_replica: new replica count after deletion
        :return bool result: flag to identify if pod deleted or not
        """
        self.log.info("[Start] deleting a data pod...")
        result = False
        self.log.info("Get pod to be deleted")
        sts_dict = self.master.get_sts_pods(pod_prefix=POD_NAME_PREFIX)
        sts_list = list(sts_dict.keys())
        self.log.debug("%s Statefulset: %s", POD_NAME_PREFIX, sts_list)
        sts = random.sample(sts_list, 1)[0]
        while len(sts_dict[sts]) == 0:
            sts = random.sample(sts_list, 1)[0]
        delete_pod = sts_dict[sts][-1]
        self.log.info("Pod to be deleted is %s", delete_pod)
        set_type, set_name = self.master.get_set_type_name(pod_name=delete_pod)
        resp = self.master.get_num_replicas(set_type, set_name)
        assert resp[0], resp
        num_replica = int(resp[1])
        num_replica-=1
        self.log.info("Shutdown data pod by replica method and "
                    "verify cluster & remaining pods status")
        resp = self.ha_obj.delete_kpod_with_shutdown_methods(
            master_node_obj=self.master, health_obj=self.hlth_master,
            delete_pod=[delete_pod], num_replica=num_replica)
        pod_name = list(resp[1].keys())[0]
        set_name = resp[1][pod_name]['deployment_name']
        self.restore_method = resp[1][pod_name]['method']
        if resp[1] is None:
            self.log.error("Failed to shutdown/delete pod: %s", resp)
        if not resp[0]:
            self.log.error("Cluster/Services status is not as expected: %s", resp)
        else:
            result = True
        self.log.info("Successfully shutdown data pod %s. Verified cluster and "
                    "services states are as expected & remaining pods status is online.", pod_name)
        self.log.info("[End] deleted a data pod...")
        return result, set_name, num_replica

    def restore_data_pod(self, set_name:str, num_replica:int):
        """
        Restore cluster safely by restoring a data pod
        :param str set_name : sts set name of data pod
        :param int num_replica : number of replicas of data pod after delete
        :return bool result: flag to identify if pod restored or not
        """
        self.log.info("[Start] Restore a data pod...")
        result = False
        resp = self.ha_obj.restore_pod(self.master, self.restore_method,
                                        restore_params={"deployment_name": None,
                                                        "deployment_backup": None,
                                                        "num_replica": num_replica+1,
                                                        "set_name": set_name})
        self.log.debug("Response: %s", resp)
        if not resp[0]:
            self.log.error("Not able to restored pod: %s", resp)
        else:
            self.log.info("Successfully restored pod by %s way", self.restore_method)
            result = True
        self.log.info("[End] Restored a data pod...")
        return result
