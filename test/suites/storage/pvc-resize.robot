*** Settings ***
Documentation       Tests related to a functional PVC after reboot

Resource            ../../resources/common.resource
Resource            ../../resources/oc.resource
Resource            ../../resources/ostree-health.resource

Suite Setup         Setup Suite With Namespace
Suite Teardown      Teardown Suite With Namespace


*** Variables ***
${SOURCE_POD}           ./assets/reboot/pod-with-pvc.yaml
${POD_NAME_STATIC}      test-pod
${RESIZE_TO}            2Gi
${PVC_CLAIM_NAME}       test-claim


*** Test Cases ***
Increase Running Pod PV Size
    [Documentation]    Increase Running Pod PV size by changing the PVC spec.
    [Setup]    Test Case Setup
    Oc Patch    pvc/${PVC_CLAIM_NAME}    '{"spec":{"resources":{"requests":{"storage":"${RESIZE_TO}"}}}}'
    Oc Wait For    pvc/${PVC_CLAIM_NAME}    jsonpath\="{.spec.resources.requests.storage}"=${RESIZE_TO}    timeout=3m
    [Teardown]    Test Case Teardown


*** Keywords ***
Test Case Setup
    [Documentation]    Prepare the cluster env and test pod workload.
    Oc Create    -f ${SOURCE_POD} -n ${NAMESPACE}
    Oc Wait For    pod/${POD_NAME_STATIC}    condition\=Ready    timeout=120s

Test Case Teardown
    [Documentation]    Clean up test suite resources
    Oc Delete    -f ${SOURCE_POD} -n ${NAMESPACE}