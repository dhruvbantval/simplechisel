/*
 * Sample runs for the "Load sample data" affordance in the empty state. These are
 * the example files from /examples, imported at build time. They are NOT loaded
 * automatically — only when the user explicitly clicks to load them — so the app
 * still "starts empty" per the product decision.
 */
import runPass from '../../examples/run_pass.json'
import runFail from '../../examples/run_fail.json'
import runMutation from '../../examples/run_mutation.json'

export const sampleRuns = [runPass, runFail, runMutation]
