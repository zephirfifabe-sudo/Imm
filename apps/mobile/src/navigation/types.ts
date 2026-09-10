import type { AnalysisRecord } from "@previsite/shared";

export type RootStackParamList = {
  Login: undefined;
  Register: undefined;
  Tabs: undefined;
  AnalysisForm: undefined;
  AnalysisResult: { analysis: AnalysisRecord };
};

export type TabParamList = {
  Home: undefined;
  History: undefined;
  Account: undefined;
};
