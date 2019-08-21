import axiosInstance from '@/plugins/axios';

const signIn = (email, password) => {
  const apiUri = '/users/signin';

  return axiosInstance.post(apiUri, {
    email,
    password,
  }, {
    dataType: 'json',
    headers: { 'Content-Type': 'application/json; charset=utf-8' },
  });
};

export default signIn;
